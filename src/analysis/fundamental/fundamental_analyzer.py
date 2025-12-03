"""
Comprehensive Fundamental Analysis Engine
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from .ratios import FinancialRatios, IndustryComparison
from .dcf_valuation import DCFValuation
from core.data_source_transparency import TransparentFinancialData

class FundamentalAnalyzer:
    """Main fundamental analysis engine"""

    # 🆕 v5.0 Phase 2: Sector EV Benchmarks (median values from market research)
    SECTOR_EV_BENCHMARKS = {
        'Technology': {'ev_revenue': 6.5, 'ev_ebitda': 20.0},
        'Healthcare': {'ev_revenue': 4.0, 'ev_ebitda': 15.0},
        'Consumer Cyclical': {'ev_revenue': 2.0, 'ev_ebitda': 12.5},
        'Consumer Defensive': {'ev_revenue': 2.0, 'ev_ebitda': 12.5},
        'Financial Services': {'ev_revenue': 3.0, 'ev_ebitda': None},  # Use P/E instead
        'Energy': {'ev_revenue': 1.5, 'ev_ebitda': 7.5},
        'Industrials': {'ev_revenue': 1.5, 'ev_ebitda': 12.5},
        'Basic Materials': {'ev_revenue': 1.5, 'ev_ebitda': 10.0},
        'Real Estate': {'ev_revenue': 10.0, 'ev_ebitda': 17.5},
        'Utilities': {'ev_revenue': 2.5, 'ev_ebitda': 11.0},
        'Communication Services': {'ev_revenue': 3.0, 'ev_ebitda': 12.5},
    }

    def __init__(self, financial_data: Dict[str, Any], current_price: float):
        """
        Initialize fundamental analyzer

        Args:
            financial_data: Financial data dictionary
            current_price: Current stock price
        """
        self.financial_data = financial_data
        self.current_price = current_price
        self.symbol = financial_data.get('symbol')
        self.sector = financial_data.get('sector')

        # Initialize components
        self.ratios_calculator = FinancialRatios(financial_data)
        self.industry_comparison = IndustryComparison(self.sector)
        self.dcf_valuation = DCFValuation(financial_data)

    def analyze(self) -> Dict[str, Any]:
        """
        Perform comprehensive fundamental analysis

        Returns:
            Dictionary containing all fundamental analysis results
        """
        logger.info(f"Starting fundamental analysis for {self.symbol}")

        try:
            # Calculate financial ratios
            ratios = self.ratios_calculator.get_all_ratios(self.current_price)

            # Perform industry comparison
            industry_comparison = self.industry_comparison.compare_ratios(ratios)
            sector_ranking = self.industry_comparison.get_sector_ranking(ratios)

            # DCF valuation with sensitivity analysis
            dcf_results = self.dcf_valuation.calculate_dcf_value()

            # NEW: Run sensitivity analysis
            dcf_sensitivity = self.dcf_valuation.sensitivity_analysis(
                wacc_range=(-0.02, 0.02, 0.005),  # ±2% WACC
                growth_range=(-0.01, 0.01, 0.005)  # ±1% growth
            )

            # Calculate DCF confidence interval
            dcf_confidence = self._calculate_dcf_confidence(dcf_sensitivity)

            # Generate DCF recommendation based on sensitivity
            dcf_recommendation = self._generate_dcf_recommendation(
                dcf_results, dcf_sensitivity, dcf_confidence
            )

            # Add to dcf_results
            dcf_results['sensitivity_analysis'] = dcf_sensitivity
            dcf_results['confidence_interval'] = dcf_confidence
            dcf_results['dcf_recommendation'] = dcf_recommendation

            # Add upside/downside calculation for web interface
            if 'intrinsic_value_per_share' in dcf_results and dcf_results['intrinsic_value_per_share']:
                intrinsic_value = dcf_results['intrinsic_value_per_share']
                upside_downside = ((intrinsic_value - self.current_price) / self.current_price) * 100
                dcf_results['upside_downside'] = upside_downside
                dcf_results['intrinsic_value'] = intrinsic_value  # Add alias for web interface

            # Calculate fundamental score
            fundamental_score = self._calculate_fundamental_score(ratios, dcf_results, sector_ranking)

            # Generate insights and recommendations
            insights = self._generate_insights(ratios, dcf_results, industry_comparison)

            # Quality assessment
            quality_assessment = self._assess_quality(ratios)

            # Risk assessment
            risk_assessment = self._assess_financial_risk(ratios)

            return {
                'symbol': self.symbol,
                'current_price': self.current_price,
                'analysis_date': datetime.now().isoformat(),

                # Core analysis results
                'financial_ratios': ratios,
                'industry_comparison': industry_comparison,
                'sector_ranking': sector_ranking,
                'dcf_valuation': dcf_results,
                'dcf_analysis': dcf_results,  # Alias for web interface compatibility

                # Scoring and recommendations
                'fundamental_score': fundamental_score,
                'overall_score': fundamental_score.get('total_score', 0),  # For web interface compatibility
                'quality_assessment': quality_assessment,
                'risk_assessment': risk_assessment,

                # Insights and summary
                'insights': insights,
                'recommendation': self._get_recommendation(fundamental_score),
                'key_strengths': self._identify_strengths(ratios, dcf_results),
                'key_concerns': self._identify_concerns(ratios, dcf_results),
                'price_targets': self._calculate_price_targets(dcf_results, ratios),

                # 🆕 v7.3.1: Include raw financial data for risk warnings
                # This ensures fields like held_percent_institutions flow through to UnifiedRecommendation
                'held_percent_institutions': self.financial_data.get('held_percent_institutions'),
                'held_percent_insiders': self.financial_data.get('held_percent_insiders'),
                'short_percent_of_float': self.financial_data.get('short_percent_of_float'),
                'short_ratio': self.financial_data.get('short_ratio'),
                'fifty_two_week_high': self.financial_data.get('fifty_two_week_high'),
                'fifty_two_week_low': self.financial_data.get('fifty_two_week_low'),
                'trailing_eps': self.financial_data.get('trailing_eps'),
                'operating_cash_flow': self.financial_data.get('operating_cash_flow'),
                'revenue_growth': self.financial_data.get('revenue_growth'),
                'debt_to_equity': self.financial_data.get('debt_to_equity')
            }

        except Exception as e:
            import traceback
            logger.error(f"Fundamental analysis failed for {self.symbol}: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {
                'symbol': self.symbol,
                'error': str(e),
                'fundamental_score': 0
            }

    def _calculate_fundamental_score(self,
                                   ratios: Dict[str, Any],
                                   dcf_results: Dict[str, Any],
                                   sector_ranking: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive fundamental score (0-10)
        """
        scores = {}
        total_score = 0
        max_score = 10

        # Valuation Score (2 points)
        valuation_score = self._score_valuation(ratios, dcf_results)
        scores['valuation'] = valuation_score
        total_score += valuation_score

        # Profitability Score (2 points)
        profitability_score = self._score_profitability(ratios)
        scores['profitability'] = profitability_score
        total_score += profitability_score

        # Financial Health Score (2 points)
        health_score = self._score_financial_health(ratios)
        scores['financial_health'] = health_score
        total_score += health_score

        # Growth Score (2 points)
        growth_score = self._score_growth(ratios)
        scores['growth'] = growth_score
        total_score += growth_score

        # Industry Comparison Score (2 points)
        industry_score = (sector_ranking.get('sector_score', 50) / 100) * 2
        scores['industry_comparison'] = industry_score
        total_score += industry_score

        return {
            'total_score': min(total_score, max_score),
            'max_score': max_score,
            'component_scores': scores,
            'rating': self._get_score_rating(total_score)
        }

    def _score_valuation(self, ratios: Dict[str, Any], dcf_results: Dict[str, Any]) -> float:
        """Score valuation attractiveness (0-2 points)"""
        score = 0

        # P/E Ratio scoring (more stringent) with null safety
        pe_ratio = ratios.get('pe_ratio')
        if pe_ratio is not None and pe_ratio > 0:
            if pe_ratio < 15:
                score += 0.6
            elif pe_ratio < 20:
                score += 0.4
            elif pe_ratio < 25:
                score += 0.2
            elif pe_ratio > 50:
                score -= 0.8  # Very overvalued
            elif pe_ratio > 30:
                score -= 0.4

        # PEG Ratio scoring (more stringent) with null safety
        peg_ratio = ratios.get('peg_ratio')
        if peg_ratio is not None and peg_ratio > 0:
            if peg_ratio < 1.0:
                score += 0.6
            elif peg_ratio < 1.5:
                score += 0.3
            elif peg_ratio < 2.0:
                score += 0.1
            elif peg_ratio > 5.0:
                score -= 0.8  # Very expensive growth
            elif peg_ratio > 3.0:
                score -= 0.4

        # DCF vs Price scoring (more penalty for overvaluation) with null safety
        dcf_value = dcf_results.get('intrinsic_value_per_share')
        if dcf_value is not None and dcf_value > 0 and self.current_price > 0:
            dcf_premium = dcf_value / self.current_price
            if dcf_premium > 1.3:
                score += 1.0  # 30%+ undervalued
            elif dcf_premium > 1.2:
                score += 0.7  # 20%+ undervalued
            elif dcf_premium > 1.1:
                score += 0.4  # 10%+ undervalued
            elif dcf_premium > 0.95:
                score += 0.1  # Fairly valued
            elif dcf_premium < 0.5:
                score -= 1.2  # 50%+ overvalued - severe penalty
            elif dcf_premium < 0.7:
                score -= 0.8  # 30%+ overvalued
            elif dcf_premium < 0.9:
                score -= 0.5  # 10%+ overvalued

        # 🆕 v5.0 Phase 2: Sector-Relative EV Scoring (replaces absolute thresholds)
        ev_score = self._score_ev_sector_relative(ratios)
        score += ev_score

        return max(0, min(score, 2))

    def _score_ev_sector_relative(self, ratios: Dict[str, Any]) -> float:
        """
        🆕 v5.0 Phase 2: Score EV ratios relative to sector benchmarks

        This provides better context than absolute thresholds:
        - Tech stocks naturally have higher EV/Revenue (6-8x is normal)
        - Energy stocks have lower EV/Revenue (1-2x is normal)
        - Comparing AAPL (EV/Rev=7x) to AMC (EV/Rev=2x) without sector context is misleading

        Returns:
            float: Score adjustment (-0.7 to +0.9)
        """
        score = 0

        # Get sector benchmark (if available)
        sector_benchmark = self.SECTOR_EV_BENCHMARKS.get(self.sector)

        if not sector_benchmark:
            logger.debug(f"No sector benchmark for '{self.sector}' - using absolute thresholds")
            # Fall back to generic absolute scoring
            ev_revenue = ratios.get('ev_revenue')
            if ev_revenue is not None and ev_revenue > 0:
                if ev_revenue < 2.0:
                    score += 0.3
                elif ev_revenue > 8.0:
                    score -= 0.5

            ev_ebitda = ratios.get('ev_ebitda')
            if ev_ebitda is not None and ev_ebitda > 0:
                if ev_ebitda < 12:
                    score += 0.4
                elif ev_ebitda > 20:
                    score -= 0.6

            return score

        # === Sector-Relative EV/Revenue Scoring ===
        ev_revenue = ratios.get('ev_revenue')
        sector_ev_revenue = sector_benchmark.get('ev_revenue')

        if ev_revenue is not None and ev_revenue > 0 and sector_ev_revenue:
            # Calculate relative premium/discount
            relative_valuation = (ev_revenue / sector_ev_revenue - 1) * 100  # % difference

            logger.debug(f"EV/Revenue: {ev_revenue:.2f}x vs sector avg {sector_ev_revenue:.2f}x ({relative_valuation:+.1f}%)")

            # Score based on relative valuation
            if relative_valuation < -40:
                score += 0.5  # 40%+ cheaper than sector → very undervalued
                logger.debug(f"   ✅ VERY CHEAP vs sector (+0.5)")
            elif relative_valuation < -20:
                score += 0.3  # 20-40% cheaper → undervalued
                logger.debug(f"   ✅ Cheap vs sector (+0.3)")
            elif relative_valuation < -10:
                score += 0.2  # 10-20% cheaper → slightly undervalued
                logger.debug(f"   ✅ Slightly cheap vs sector (+0.2)")
            elif relative_valuation > 50:
                score -= 0.6  # 50%+ more expensive → very overvalued
                logger.debug(f"   ❌ VERY EXPENSIVE vs sector (-0.6)")
            elif relative_valuation > 25:
                score -= 0.4  # 25-50% more expensive → overvalued
                logger.debug(f"   ❌ Expensive vs sector (-0.4)")
            elif relative_valuation > 10:
                score -= 0.2  # 10-25% more expensive → slightly overvalued
                logger.debug(f"   ⚠️  Slightly expensive vs sector (-0.2)")
            else:
                logger.debug(f"   ➡️  Fair value vs sector (±10%)")

        # === Sector-Relative EV/EBITDA Scoring ===
        ev_ebitda = ratios.get('ev_ebitda')
        sector_ev_ebitda = sector_benchmark.get('ev_ebitda')

        if ev_ebitda is not None and ev_ebitda > 0 and sector_ev_ebitda:
            # Calculate relative premium/discount
            relative_valuation = (ev_ebitda / sector_ev_ebitda - 1) * 100

            logger.debug(f"EV/EBITDA: {ev_ebitda:.2f}x vs sector avg {sector_ev_ebitda:.2f}x ({relative_valuation:+.1f}%)")

            # Score based on relative valuation
            if relative_valuation < -40:
                score += 0.4  # 40%+ cheaper than sector
                logger.debug(f"   ✅ VERY CHEAP vs sector (+0.4)")
            elif relative_valuation < -20:
                score += 0.3  # 20-40% cheaper
                logger.debug(f"   ✅ Cheap vs sector (+0.3)")
            elif relative_valuation < -10:
                score += 0.1  # 10-20% cheaper
                logger.debug(f"   ✅ Slightly cheap vs sector (+0.1)")
            elif relative_valuation > 50:
                score -= 0.7  # 50%+ more expensive
                logger.debug(f"   ❌ VERY EXPENSIVE vs sector (-0.7)")
            elif relative_valuation > 25:
                score -= 0.4  # 25-50% more expensive
                logger.debug(f"   ❌ Expensive vs sector (-0.4)")
            elif relative_valuation > 10:
                score -= 0.2  # 10-25% more expensive
                logger.debug(f"   ⚠️  Slightly expensive vs sector (-0.2)")
            else:
                logger.debug(f"   ➡️  Fair value vs sector (±10%)")

        return score

    def _score_profitability(self, ratios: Dict[str, Any]) -> float:
        """Score profitability (0-2 points)"""
        score = 0

        # Helper function to normalize percentage values
        def normalize_percentage(value):
            """Convert percentage to decimal if needed"""
            if value is None:
                return None
            try:
                # If value > 1, assume it's in percentage form, convert to decimal
                if abs(float(value)) > 1:
                    return float(value) / 100
                return float(value)
            except (TypeError, ValueError):
                return None

        # ROE scoring (more stringent)
        roe = normalize_percentage(ratios.get('roe'))
        if roe is not None:
            if roe > 0.20:
                score += 0.7
            elif roe > 0.15:
                score += 0.5
            elif roe > 0.10:
                score += 0.3
            elif roe > 0.05:
                score += 0.1
            elif roe < 0:
                score -= 0.8
            else:  # Very low positive ROE (0-5%)
                score -= 0.3

        # Profit Margin scoring (more stringent)
        profit_margin = normalize_percentage(ratios.get('profit_margin'))
        if profit_margin is not None:
            if profit_margin > 0.15:
                score += 0.7
            elif profit_margin > 0.10:
                score += 0.5
            elif profit_margin > 0.05:
                score += 0.3
            elif profit_margin > 0.01:
                score += 0.1
            elif profit_margin < 0:
                score -= 0.8
            else:  # Very low positive margin (0-1%)
                score -= 0.4

        # ROA scoring (more stringent)
        roa = normalize_percentage(ratios.get('roa'))
        if roa is not None:
            if roa > 0.08:
                score += 0.6
            elif roa > 0.05:
                score += 0.4
            elif roa > 0.02:
                score += 0.2
            elif roa > 0.005:
                score += 0.1
            elif roa < 0:
                score -= 0.6
            else:  # Very low positive ROA (0-0.5%)
                score -= 0.3

        return max(0, min(score, 2))

    def _score_financial_health(self, ratios: Dict[str, Any]) -> float:
        """Score financial health (0-2 points)"""
        score = 0

        # Debt-to-Equity scoring
        debt_to_equity = ratios.get('debt_to_equity')
        if debt_to_equity is not None:
            if debt_to_equity < 0.3:
                score += 0.7
            elif debt_to_equity < 1.0:
                score += 0.5
            elif debt_to_equity < 2.0:
                score += 0.2
            else:
                score -= 0.3

        # Current Ratio scoring with null safety
        current_ratio = ratios.get('current_ratio')
        if current_ratio is not None and current_ratio > 0:
            if current_ratio > 2.0:
                score += 0.6
            elif current_ratio > 1.5:
                score += 0.5
            elif current_ratio > 1.0:
                score += 0.3
            else:
                score -= 0.5

        # Interest Coverage scoring with null safety
        interest_coverage = ratios.get('interest_coverage')
        if interest_coverage is not None and interest_coverage > 0:
            if interest_coverage > 5:
                score += 0.7
            elif interest_coverage > 2:
                score += 0.5
            elif interest_coverage > 1:
                score += 0.2
            else:
                score -= 0.5

        return max(0, min(score, 2))

    def _score_growth(self, ratios: Dict[str, Any]) -> float:
        """Score growth prospects (0-2 points)"""
        score = 0

        # Revenue Growth scoring with null safety
        revenue_growth = ratios.get('revenue_growth')
        if revenue_growth is not None:
            if revenue_growth > 0.15:
                score += 1.0
            elif revenue_growth > 0.10:
                score += 0.7
            elif revenue_growth > 0.05:
                score += 0.5
            elif revenue_growth < 0:
                score -= 0.5

        # Earnings Growth scoring with null safety
        earnings_growth = ratios.get('earnings_growth')
        if earnings_growth is not None:
            if earnings_growth > 0.20:
                score += 1.0
            elif earnings_growth > 0.15:
                score += 0.7
            elif earnings_growth > 0.10:
                score += 0.5
            elif earnings_growth < 0:
                score -= 0.5

        return max(0, min(score, 2))

    def _get_score_rating(self, score: float) -> str:
        """Convert score to rating"""
        if score >= 8.5:
            return "Excellent"
        elif score >= 7.0:
            return "Good"
        elif score >= 5.0:
            return "Fair"
        elif score >= 3.0:
            return "Poor"
        else:
            return "Very Poor"

    def _generate_insights(self,
                          ratios: Dict[str, Any],
                          dcf_results: Dict[str, Any],
                          industry_comparison: Dict[str, Any]) -> List[str]:
        """Generate actionable insights"""
        insights = []

        # Valuation insights with null safety
        dcf_value = dcf_results.get('intrinsic_value_per_share')
        if dcf_value is not None and dcf_value > 0 and self.current_price > 0:
            if dcf_value > self.current_price * 1.2:
                insights.append(f"DCF suggests stock is undervalued by {((dcf_value / self.current_price - 1) * 100):.1f}%")
            elif dcf_value < self.current_price * 0.8:
                insights.append(f"DCF suggests stock is overvalued by {((1 - dcf_value / self.current_price) * 100):.1f}%")

        # Profitability insights with null safety
        roe = ratios.get('roe')
        if roe is not None and roe > 0.20:
            insights.append(f"Excellent ROE of {roe*100:.1f}% indicates highly efficient use of equity")

        # Growth insights with null safety
        revenue_growth = ratios.get('revenue_growth')
        earnings_growth = ratios.get('earnings_growth')
        if revenue_growth is not None and earnings_growth is not None:
            if earnings_growth > revenue_growth * 1.5:
                insights.append("Earnings growing faster than revenue suggests improving operational efficiency")

        # Industry comparison insights
        for ratio_name, ratio_data in industry_comparison.get('ratios', {}).items():
            if ratio_data['performance_vs_industry'] == "Better" and ratio_data.get('relative_performance', 0) > 1.5:
                insights.append(f"Significantly outperforms industry average in {ratio_name}")

        return insights

    def _assess_quality(self, ratios: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall business quality"""
        quality_factors = {}

        # Profitability consistency with null safety
        roe = ratios.get('roe')
        profit_margin = ratios.get('profit_margin')

        quality_factors['profitability_grade'] = self._grade_profitability(roe, profit_margin)

        # Financial stability with null safety
        debt_to_equity = ratios.get('debt_to_equity')
        current_ratio = ratios.get('current_ratio')

        quality_factors['stability_grade'] = self._grade_stability(debt_to_equity, current_ratio)

        # Growth quality with null safety
        revenue_growth = ratios.get('revenue_growth')
        earnings_growth = ratios.get('earnings_growth')

        quality_factors['growth_grade'] = self._grade_growth(revenue_growth, earnings_growth)

        # Overall quality score
        grades = [quality_factors['profitability_grade'], quality_factors['stability_grade'], quality_factors['growth_grade']]
        quality_factors['overall_grade'] = sum(grades) / len(grades)

        return quality_factors

    def _calculate_dcf_confidence(self, sensitivity: Dict) -> Dict[str, Any]:
        """Calculate confidence interval from DCF sensitivity analysis"""
        if not sensitivity or 'min_value' not in sensitivity:
            return {}

        return {
            'low_estimate': sensitivity.get('min_value'),   # Worst case
            'base_estimate': sensitivity.get('base_intrinsic_value'),
            'high_estimate': sensitivity.get('max_value'),  # Best case
            'mean_estimate': sensitivity.get('mean_value'),
            'std_dev': sensitivity.get('std_value'),
            'confidence_95': {
                'lower': sensitivity.get('mean_value', 0) - 1.96 * sensitivity.get('std_value', 0),
                'upper': sensitivity.get('mean_value', 0) + 1.96 * sensitivity.get('std_value', 0)
            } if sensitivity.get('mean_value') and sensitivity.get('std_value') else None
        }

    def _generate_dcf_recommendation(self, base_dcf: Dict, sensitivity: Dict,
                                    confidence: Dict) -> Dict[str, Any]:
        """Generate recommendation based on DCF sensitivity analysis"""
        if not confidence or not confidence.get('low_estimate'):
            return {'verdict': 'UNKNOWN', 'reason': 'Insufficient DCF data'}

        current_price = self.current_price
        base_value = base_dcf.get('intrinsic_value_per_share', 0)

        # Check if current price is below even the worst case
        if current_price < confidence['low_estimate']:
            margin = ((confidence['low_estimate'] - current_price) / current_price) * 100
            return {
                'verdict': 'STRONG_BUY',
                'reason': f'Price ${current_price:.2f} below worst-case estimate ${confidence["low_estimate"]:.2f}',
                'margin_of_safety': round(margin, 1),
                'confidence_level': 'Very High'
            }

        # Check if within confidence interval
        if confidence.get('confidence_95'):
            lower = confidence['confidence_95']['lower']
            upper = confidence['confidence_95']['upper']
            if lower <= current_price <= upper:
                return {
                    'verdict': 'FAIRLY_VALUED',
                    'reason': f'Price within 95% confidence interval (${lower:.2f} - ${upper:.2f})',
                    'margin_of_safety': 0,
                    'confidence_level': 'Medium'
                }

        # Check if above best case
        if current_price > confidence['high_estimate']:
            overvaluation = ((current_price - confidence['high_estimate']) / current_price) * 100
            return {
                'verdict': 'OVERVALUED',
                'reason': f'Price ${current_price:.2f} above best-case estimate ${confidence["high_estimate"]:.2f}',
                'margin_of_safety': round(-overvaluation, 1),
                'confidence_level': 'High'
            }

        # Default: use base case
        margin = ((base_value - current_price) / current_price) * 100
        if margin > 20:
            return {
                'verdict': 'BUY',
                'reason': f'Base case shows {margin:.1f}% upside',
                'margin_of_safety': round(margin, 1),
                'confidence_level': 'Medium'
            }
        elif margin < -20:
            return {
                'verdict': 'SELL',
                'reason': f'Base case shows {abs(margin):.1f}% downside',
                'margin_of_safety': round(margin, 1),
                'confidence_level': 'Medium'
            }
        else:
            return {
                'verdict': 'HOLD',
                'reason': f'Within ±20% of base case (margin: {margin:.1f}%)',
                'margin_of_safety': round(margin, 1),
                'confidence_level': 'Low'
            }

    def _assess_financial_risk(self, ratios: Dict[str, Any]) -> Dict[str, Any]:
        """Assess financial risk factors"""
        risk_factors = {}

        # Leverage risk with null safety
        debt_to_equity = ratios.get('debt_to_equity')
        if debt_to_equity is not None:
            if debt_to_equity > 2.0:
                risk_factors['leverage_risk'] = "High"
            elif debt_to_equity > 1.0:
                risk_factors['leverage_risk'] = "Moderate"
            else:
                risk_factors['leverage_risk'] = "Low"
        else:
            risk_factors['leverage_risk'] = "Unknown"

        # Liquidity risk with null safety
        current_ratio = ratios.get('current_ratio')
        if current_ratio is not None:
            if current_ratio < 1.0:
                risk_factors['liquidity_risk'] = "High"
            elif current_ratio < 1.5:
                risk_factors['liquidity_risk'] = "Moderate"
            else:
                risk_factors['liquidity_risk'] = "Low"
        else:
            risk_factors['liquidity_risk'] = "Unknown"

        # Profitability risk with null safety
        profit_margin = ratios.get('profit_margin')
        if profit_margin is not None:
            if profit_margin < 0:
                risk_factors['profitability_risk'] = "High"
            elif profit_margin < 0.05:
                risk_factors['profitability_risk'] = "Moderate"
            else:
                risk_factors['profitability_risk'] = "Low"
        else:
            risk_factors['profitability_risk'] = "Unknown"

        return risk_factors

    def _get_recommendation(self, fundamental_score: Dict[str, Any]) -> str:
        """Get investment recommendation based on fundamental score"""
        score = fundamental_score['total_score']

        if score >= 8.5:
            return "Strong Buy"
        elif score >= 7.0:
            return "Buy"
        elif score >= 5.0:
            return "Hold"
        elif score >= 3.0:
            return "Sell"
        else:
            return "Strong Sell"

    def _identify_strengths(self, ratios: Dict[str, Any], dcf_results: Dict[str, Any]) -> List[str]:
        """Identify key strengths"""
        strengths = []

        roe = ratios.get('roe')
        if roe is not None and roe > 0.20:
            strengths.append("High return on equity")

        debt_to_equity = ratios.get('debt_to_equity')
        if debt_to_equity is not None and debt_to_equity < 0.3:
            strengths.append("Low debt levels")

        current_ratio = ratios.get('current_ratio')
        if current_ratio is not None and current_ratio > 2.0:
            strengths.append("Strong liquidity position")

        dcf_value = dcf_results.get('intrinsic_value_per_share')
        if dcf_value is not None and dcf_value > 0 and self.current_price > 0 and dcf_value > self.current_price * 1.15:
            strengths.append("Undervalued based on DCF analysis")

        revenue_growth = ratios.get('revenue_growth')
        if revenue_growth is not None and revenue_growth > 0.10:
            strengths.append("Strong revenue growth")

        return strengths

    def _identify_concerns(self, ratios: Dict[str, Any], dcf_results: Dict[str, Any]) -> List[str]:
        """Identify key concerns"""
        concerns = []

        debt_to_equity = ratios.get('debt_to_equity')
        if debt_to_equity is not None and debt_to_equity > 2.0:
            concerns.append("High debt levels")

        current_ratio = ratios.get('current_ratio')
        if current_ratio is not None and current_ratio < 1.0:
            concerns.append("Potential liquidity issues")

        profit_margin = ratios.get('profit_margin')
        if profit_margin is not None and profit_margin < 0:
            concerns.append("Negative profit margins")

        dcf_value = dcf_results.get('intrinsic_value_per_share')
        if dcf_value is not None and dcf_value > 0 and self.current_price > 0 and dcf_value < self.current_price * 0.85:
            concerns.append("Overvalued based on DCF analysis")

        revenue_growth = ratios.get('revenue_growth')
        if revenue_growth is not None and revenue_growth < 0:
            concerns.append("Declining revenue")

        return concerns

    def _calculate_price_targets(self, dcf_results: Dict[str, Any], ratios: Dict[str, Any]) -> Dict[str, float]:
        """Calculate price targets"""
        targets = {}

        # DCF-based target with null safety
        dcf_value = dcf_results.get('intrinsic_value_per_share')
        if dcf_value is not None and dcf_value > 0:
            targets['dcf_target'] = dcf_value

        # P/E-based target with null safety
        eps = ratios.get('eps')
        if eps is not None and eps > 0:
            # Use industry average P/E
            industry_pe = 18.0  # Default
            targets['pe_target'] = eps * industry_pe

        # Conservative target (lowest of all methods)
        all_targets = [v for v in targets.values() if v is not None and v > 0]
        if all_targets:
            targets['conservative_target'] = min(all_targets)
            targets['optimistic_target'] = max(all_targets)

        return targets

    def _grade_profitability(self, roe: float, profit_margin: float) -> float:
        """Grade profitability (0-10)"""
        roe_score = min(roe * 50, 5) if roe is not None and roe > 0 else 0  # ROE to 5 points
        margin_score = min(profit_margin * 50, 5) if profit_margin is not None and profit_margin > 0 else 0  # Margin to 5 points
        return min(roe_score + margin_score, 10)

    def _grade_stability(self, debt_to_equity: float, current_ratio: float) -> float:
        """Grade financial stability (0-10)"""
        debt_score = max(5 - debt_to_equity * 2.5, 0) if debt_to_equity is not None else 2.5  # Lower debt = higher score, default score if None
        liquidity_score = min(current_ratio * 2.5, 5) if current_ratio is not None else 0  # Higher current ratio = higher score
        return min(debt_score + liquidity_score, 10)

    def _grade_growth(self, revenue_growth: float, earnings_growth: float) -> float:
        """Grade growth quality (0-10)"""
        if revenue_growth is None:
            revenue_growth = 0
        if earnings_growth is None:
            earnings_growth = 0

        revenue_score = min(revenue_growth * 25, 5) if revenue_growth > 0 else 0
        earnings_score = min(earnings_growth * 20, 5) if earnings_growth > 0 else 0
        return min(revenue_score + earnings_score, 10)

    def calculate_basic_fundamentals(self, financial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate basic fundamental metrics for fast screening

        Args:
            financial_data: Financial data dictionary

        Returns:
            Basic fundamental analysis results
        """
        try:
            if not financial_data:
                return {'basic_score': 5.0}

            # Extract basic metrics with null safety
            pe_ratio = financial_data.get('pe_ratio')
            market_cap = financial_data.get('market_cap')
            revenue_growth = financial_data.get('revenue_growth')
            profit_margin = financial_data.get('profit_margin')
            debt_to_equity = financial_data.get('debt_to_equity')
            dividend_yield = financial_data.get('dividend_yield')
            roe = financial_data.get('roe')

            # Basic scoring
            score = 5.0  # Start with neutral

            # P/E ratio scoring
            if pe_ratio is not None:
                if 10 <= pe_ratio <= 20:  # Reasonable range
                    score += 1.0
                elif pe_ratio < 10:  # Potentially undervalued
                    score += 0.5
                elif pe_ratio > 25:  # Potentially overvalued
                    score -= 0.5

            # Market cap (stability factor)
            if market_cap is not None:
                if market_cap > 10000000000:  # Large cap > $10B
                    score += 0.5
                elif market_cap > 2000000000:  # Mid cap > $2B
                    score += 0.3

            # Revenue growth
            if revenue_growth is not None and revenue_growth > 0:
                if revenue_growth > 10:  # > 10% growth
                    score += 1.0
                elif revenue_growth > 5:  # > 5% growth
                    score += 0.5

            # Profitability
            if profit_margin is not None and profit_margin > 0:
                if profit_margin > 15:  # > 15% margin
                    score += 1.0
                elif profit_margin > 8:  # > 8% margin
                    score += 0.5

            # ROE
            if roe is not None and roe > 0:
                if roe > 15:  # > 15% ROE
                    score += 0.5
                elif roe > 10:  # > 10% ROE
                    score += 0.3

            # Debt management
            if debt_to_equity is not None:
                if debt_to_equity < 0.3:  # Low debt
                    score += 0.5
                elif debt_to_equity > 1.0:  # High debt
                    score -= 0.5

            # Dividend (if any)
            if dividend_yield is not None and dividend_yield > 0:
                score += 0.3  # Bonus for paying dividends

            # Ensure score is within bounds
            basic_score = max(1.0, min(10.0, score))

            return {
                'basic_score': basic_score,
                'pe_ratio': pe_ratio,
                'market_cap': market_cap,
                'revenue_growth': revenue_growth,
                'profit_margin': profit_margin,
                'debt_to_equity': debt_to_equity,
                'dividend_yield': dividend_yield,
                'roe': roe
            }

        except Exception as e:
            logger.error(f"Basic fundamentals calculation failed: {e}")
            return {'basic_score': 5.0}