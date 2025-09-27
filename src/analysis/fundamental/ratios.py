"""
Fundamental Analysis - Financial Ratios Calculator
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger


class FinancialRatios:
    """Calculate and analyze financial ratios"""

    def __init__(self, financial_data: Dict[str, Any]):
        """
        Initialize with financial data

        Args:
            financial_data: Dictionary containing financial information
        """
        self.data = financial_data
        self.symbol = financial_data.get('symbol')

    def calculate_valuation_ratios(self, current_price: float) -> Dict[str, Any]:
        """
        Calculate valuation ratios

        Args:
            current_price: Current stock price

        Returns:
            Dictionary containing valuation ratios
        """
        ratios = {}

        # P/E Ratio
        eps = self.data.get('eps')
        if eps and eps > 0:
            ratios['pe_ratio'] = current_price / eps
        else:
            ratios['pe_ratio'] = None

        # P/B Ratio
        book_value_per_share = self.data.get('book_value_per_share')
        if book_value_per_share and book_value_per_share > 0:
            ratios['pb_ratio'] = current_price / book_value_per_share
        else:
            ratios['pb_ratio'] = None

        # P/S Ratio
        revenue_per_share = self._calculate_revenue_per_share()
        if revenue_per_share and revenue_per_share > 0:
            ratios['ps_ratio'] = current_price / revenue_per_share
        else:
            ratios['ps_ratio'] = None

        # PEG Ratio
        eps_growth = self.data.get('earnings_growth') or self.data.get('eps_growth')
        if ratios.get('pe_ratio') and eps_growth and eps_growth > 0:
            ratios['peg_ratio'] = ratios['pe_ratio'] / (eps_growth * 100)
        else:
            ratios['peg_ratio'] = None

        # EV/Revenue
        enterprise_value = self.data.get('enterprise_value')
        revenue = self.data.get('revenue')
        if enterprise_value and revenue and revenue > 0:
            ratios['ev_revenue'] = enterprise_value / revenue
        else:
            ratios['ev_revenue'] = None

        # EV/EBITDA
        ebitda = self.data.get('ebitda')
        if enterprise_value and ebitda and ebitda > 0:
            ratios['ev_ebitda'] = enterprise_value / ebitda
        else:
            ratios['ev_ebitda'] = None

        return ratios

    def calculate_profitability_ratios(self) -> Dict[str, Any]:
        """
        Calculate profitability ratios

        Returns:
            Dictionary containing profitability ratios
        """
        ratios = {}

        # ROE (Return on Equity)
        net_income = self.data.get('net_income')
        shareholders_equity = self.data.get('shareholders_equity')
        roe_raw = self.data.get('return_on_equity')

        # Try direct calculation first
        calculated_roe = None
        if net_income and shareholders_equity and shareholders_equity > 0:
            calculated_roe = net_income / shareholders_equity

        # Use fallback if calculation seems unreasonable (>100% or <-50%) or if calculation failed
        if (calculated_roe is None or
            calculated_roe > 1.0 or
            calculated_roe < -0.5):

            if roe_raw is not None:
                # Convert from percentage to decimal if needed (values > 1 are assumed to be percentages)
                if abs(roe_raw) > 1:
                    ratios['roe'] = roe_raw / 100
                else:
                    ratios['roe'] = roe_raw
            else:
                ratios['roe'] = calculated_roe  # Use calculated even if unreasonable
        else:
            ratios['roe'] = calculated_roe

        # ROA (Return on Assets)
        total_assets = self.data.get('total_assets')
        if net_income and total_assets and total_assets > 0:
            ratios['roa'] = net_income / total_assets
        else:
            # Fallback to return_on_assets from data source
            roa_raw = self.data.get('return_on_assets')
            if roa_raw is not None:
                # Convert from percentage to decimal if needed (values > 1 are assumed to be percentages)
                if abs(roa_raw) > 1:
                    ratios['roa'] = roa_raw / 100
                else:
                    ratios['roa'] = roa_raw
            else:
                ratios['roa'] = None

        # ROIC (Return on Invested Capital)
        ratios['roic'] = self._calculate_roic()

        # Profit Margin
        revenue = self.data.get('revenue')
        if net_income and revenue and revenue > 0:
            ratios['profit_margin'] = net_income / revenue
        else:
            ratios['profit_margin'] = self.data.get('profit_margin')

        # Operating Margin
        operating_income = self.data.get('operating_income')
        if operating_income and revenue and revenue > 0:
            ratios['operating_margin'] = operating_income / revenue
        else:
            ratios['operating_margin'] = self.data.get('operating_margin')

        # Gross Margin
        gross_profit = self.data.get('gross_profit')
        if gross_profit and revenue and revenue > 0:
            ratios['gross_margin'] = gross_profit / revenue
        else:
            # Calculate from profit margin if available
            profit_margin = self.data.get('profit_margin')
            if profit_margin:
                ratios['gross_margin'] = profit_margin * 1.5  # Rough estimate
            else:
                ratios['gross_margin'] = None

        return ratios

    def calculate_financial_health_ratios(self) -> Dict[str, Any]:
        """
        Calculate financial health and solvency ratios

        Returns:
            Dictionary containing financial health ratios
        """
        ratios = {}

        # Debt-to-Equity Ratio
        total_debt = self.data.get('total_debt')
        shareholders_equity = self.data.get('shareholders_equity')

        if total_debt and shareholders_equity and shareholders_equity > 0:
            ratios['debt_to_equity'] = total_debt / shareholders_equity
        else:
            ratios['debt_to_equity'] = self.data.get('debt_to_equity')

        # Current Ratio
        current_assets = self.data.get('current_assets')
        current_liabilities = self.data.get('current_liabilities')

        if current_assets and current_liabilities and current_liabilities > 0:
            ratios['current_ratio'] = current_assets / current_liabilities
        else:
            ratios['current_ratio'] = self.data.get('current_ratio')

        # Quick Ratio
        cash_and_equivalents = self.data.get('cash_and_equivalents', 0)
        if current_assets and current_liabilities and current_liabilities > 0:
            # Approximate quick ratio (excludes inventory)
            ratios['quick_ratio'] = (current_assets * 0.8) / current_liabilities
        else:
            ratios['quick_ratio'] = self.data.get('quick_ratio')

        # Interest Coverage Ratio
        ratios['interest_coverage'] = self._calculate_interest_coverage()

        # Debt-to-Assets Ratio
        total_assets = self.data.get('total_assets')
        if total_debt and total_assets and total_assets > 0:
            ratios['debt_to_assets'] = total_debt / total_assets
        else:
            ratios['debt_to_assets'] = None

        return ratios

    def calculate_growth_ratios(self) -> Dict[str, Any]:
        """
        Calculate growth ratios

        Returns:
            Dictionary containing growth ratios
        """
        ratios = {}

        # Revenue Growth
        ratios['revenue_growth'] = self.data.get('revenue_growth')

        # Earnings Growth
        ratios['earnings_growth'] = self.data.get('earnings_growth') or self.data.get('eps_growth')

        # Get historical data for manual calculation if needed
        # This would require historical financial data which is complex
        # For now, use provided growth rates

        return ratios

    def calculate_dividend_ratios(self, current_price: float) -> Dict[str, Any]:
        """
        Calculate dividend-related ratios

        Args:
            current_price: Current stock price

        Returns:
            Dictionary containing dividend ratios
        """
        ratios = {}

        # Dividend Yield
        dividend_per_share = self.data.get('dividend_per_share') or 0
        if dividend_per_share and current_price > 0:
            ratios['dividend_yield'] = dividend_per_share / current_price
        else:
            ratios['dividend_yield'] = self.data.get('dividend_yield')

        # Payout Ratio
        eps = self.data.get('eps')
        if dividend_per_share and eps and eps > 0:
            ratios['payout_ratio'] = dividend_per_share / eps
        else:
            ratios['payout_ratio'] = self.data.get('payout_ratio')

        return ratios

    def get_all_ratios(self, current_price: float) -> Dict[str, Any]:
        """
        Calculate all financial ratios

        Args:
            current_price: Current stock price

        Returns:
            Dictionary containing all ratios
        """
        all_ratios = {
            'symbol': self.symbol,
            'current_price': current_price,
            'calculation_date': datetime.now().isoformat(),
        }

        # Calculate all ratio categories
        all_ratios.update(self.calculate_valuation_ratios(current_price))
        all_ratios.update(self.calculate_profitability_ratios())
        all_ratios.update(self.calculate_financial_health_ratios())
        all_ratios.update(self.calculate_growth_ratios())
        all_ratios.update(self.calculate_dividend_ratios(current_price))

        return all_ratios

    def _calculate_revenue_per_share(self) -> Optional[float]:
        """Calculate revenue per share"""
        revenue = self.data.get('revenue')
        shares_outstanding = self.data.get('shares_outstanding')

        if revenue and shares_outstanding and shares_outstanding > 0:
            return revenue / shares_outstanding
        return None

    def _calculate_roic(self) -> Optional[float]:
        """Calculate Return on Invested Capital"""
        net_income = self.data.get('net_income')
        interest_expense = self.data.get('interest_expense', 0)

        # Estimate tax rate
        tax_rate = 0.25  # Default corporate tax rate

        # NOPAT = Net Operating Profit After Tax
        if net_income and interest_expense:
            nopat = net_income + (interest_expense * (1 - tax_rate))
        elif net_income:
            nopat = net_income
        else:
            return None

        # Invested Capital = Total Assets - Current Liabilities (excluding debt)
        total_assets = self.data.get('total_assets')
        current_liabilities = self.data.get('current_liabilities')

        if total_assets and current_liabilities:
            invested_capital = total_assets - current_liabilities
            if invested_capital > 0:
                return nopat / invested_capital

        return None

    def _calculate_interest_coverage(self) -> Optional[float]:
        """Calculate Interest Coverage Ratio"""
        # Try to get EBIT
        operating_income = self.data.get('operating_income')
        interest_expense = self.data.get('interest_expense')

        if operating_income and interest_expense and interest_expense > 0:
            return operating_income / interest_expense

        # Alternative: use provided interest coverage
        return self.data.get('interest_coverage')


class IndustryComparison:
    """Compare ratios against industry averages"""

    # Industry average ratios (simplified - in practice, these would come from a database)
    INDUSTRY_AVERAGES = {
        'Technology': {
            'pe_ratio': 25.0,
            'pb_ratio': 4.0,
            'ps_ratio': 6.0,
            'roe': 0.20,
            'roa': 0.08,
            'debt_to_equity': 0.30,
            'profit_margin': 0.15,
        },
        'Healthcare': {
            'pe_ratio': 18.0,
            'pb_ratio': 3.0,
            'ps_ratio': 4.0,
            'roe': 0.15,
            'roa': 0.06,
            'debt_to_equity': 0.40,
            'profit_margin': 0.12,
        },
        'Financials': {
            'pe_ratio': 12.0,
            'pb_ratio': 1.2,
            'ps_ratio': 2.5,
            'roe': 0.12,
            'roa': 0.01,
            'debt_to_equity': 2.0,
            'profit_margin': 0.20,
        },
        'Consumer Discretionary': {
            'pe_ratio': 20.0,
            'pb_ratio': 2.5,
            'ps_ratio': 1.8,
            'roe': 0.18,
            'roa': 0.05,
            'debt_to_equity': 0.60,
            'profit_margin': 0.08,
        },
        'default': {
            'pe_ratio': 18.0,
            'pb_ratio': 2.5,
            'ps_ratio': 3.0,
            'roe': 0.15,
            'roa': 0.05,
            'debt_to_equity': 0.50,
            'profit_margin': 0.10,
        }
    }

    def __init__(self, sector: str = None):
        """
        Initialize industry comparison

        Args:
            sector: Company sector
        """
        self.sector = sector
        self.industry_avg = self.INDUSTRY_AVERAGES.get(sector, self.INDUSTRY_AVERAGES['default'])

    def compare_ratios(self, company_ratios: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare company ratios against industry averages

        Args:
            company_ratios: Dictionary of company financial ratios

        Returns:
            Dictionary containing comparison results
        """
        comparison = {
            'sector': self.sector,
            'comparison_date': datetime.now().isoformat(),
            'ratios': {}
        }

        for ratio_name, industry_value in self.industry_avg.items():
            company_value = company_ratios.get(ratio_name)

            if company_value is not None and industry_value is not None:
                # Calculate relative performance
                if ratio_name in ['debt_to_equity']:
                    # Lower is better for debt ratios
                    relative_performance = industry_value / company_value if company_value > 0 else None
                    performance_vs_industry = "Better" if company_value < industry_value else "Worse"
                else:
                    # Higher is better for most ratios
                    relative_performance = company_value / industry_value if industry_value > 0 else None
                    performance_vs_industry = "Better" if company_value > industry_value else "Worse"

                comparison['ratios'][ratio_name] = {
                    'company_value': company_value,
                    'industry_average': industry_value,
                    'relative_performance': relative_performance,
                    'performance_vs_industry': performance_vs_industry,
                    'difference_percent': ((company_value - industry_value) / industry_value * 100) if industry_value != 0 else None
                }

        return comparison

    def get_sector_ranking(self, company_ratios: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get overall sector ranking

        Args:
            company_ratios: Company ratios

        Returns:
            Dictionary containing sector ranking
        """
        comparison = self.compare_ratios(company_ratios)

        # Calculate overall score
        better_count = 0
        total_count = 0

        for ratio_data in comparison['ratios'].values():
            if ratio_data['performance_vs_industry'] == "Better":
                better_count += 1
            total_count += 1

        sector_score = (better_count / total_count * 100) if total_count > 0 else 0

        return {
            'sector_score': sector_score,
            'better_than_industry': better_count,
            'total_ratios_compared': total_count,
            'ranking': self._get_ranking_description(sector_score)
        }

    def _get_ranking_description(self, score: float) -> str:
        """Get ranking description based on score"""
        if score >= 80:
            return "Top Performer"
        elif score >= 60:
            return "Above Average"
        elif score >= 40:
            return "Average"
        elif score >= 20:
            return "Below Average"
        else:
            return "Poor Performer"