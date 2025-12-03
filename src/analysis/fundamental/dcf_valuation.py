"""
DCF (Discounted Cash Flow) Valuation Model
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

class DCFValuation:
    """Discounted Cash Flow valuation model"""

    def __init__(self, financial_data: Dict[str, Any]):
        """
        Initialize DCF model

        Args:
            financial_data: Dictionary containing financial data
        """
        self.data = financial_data
        self.symbol = financial_data.get('symbol')

    def calculate_dcf_value(self,
                           projection_years: int = 5,
                           terminal_growth_rate: float = 0.02,  # Reduced to 2% (more conservative)
                           risk_free_rate: float = 0.03,
                           market_risk_premium: float = 0.06) -> Dict[str, Any]:
        """
        Calculate DCF intrinsic value

        Args:
            projection_years: Number of years to project
            terminal_growth_rate: Long-term growth rate (default 2.5%)
            risk_free_rate: Risk-free rate (default 3%)
            market_risk_premium: Market risk premium (default 6%)

        Returns:
            Dictionary containing DCF results
        """
        try:
            # Step 1: Calculate WACC
            wacc = self._calculate_wacc(risk_free_rate, market_risk_premium)

            # Step 2: Project Free Cash Flows
            projected_fcf = self._project_free_cash_flows(projection_years)

            # Step 3: Calculate terminal value
            terminal_value = self._calculate_terminal_value(
                projected_fcf[-1], terminal_growth_rate, wacc
            )

            # Step 4: Discount cash flows to present value
            pv_fcf = self._discount_cash_flows(projected_fcf, wacc)
            pv_terminal = terminal_value / ((1 + wacc) ** projection_years)

            # Step 5: Calculate enterprise value
            enterprise_value = sum(pv_fcf) + pv_terminal

            # Step 6: Calculate equity value
            equity_value = self._calculate_equity_value(enterprise_value)

            # Step 7: Calculate per-share value
            shares_outstanding = self.data.get('shares_outstanding')
            if not shares_outstanding or shares_outstanding <= 0:
                shares_outstanding = self.data.get('market_cap', 0) / self.data.get('current_price', 1)

            intrinsic_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

            # Final sanity check: cap intrinsic value at reasonable multiple of current price
            current_price = self.data.get('current_price') or 0
            if not current_price and self.data.get('market_cap') and shares_outstanding:
                market_cap_val = self.data.get('market_cap') or 0
                current_price = market_cap_val / shares_outstanding if shares_outstanding > 0 else 0

            # Ensure current_price is never None
            current_price = current_price or 0

            if current_price > 0 and intrinsic_value_per_share > current_price * 5:
                # Cap at 5x current price for extreme valuations
                logger.warning(f"DCF intrinsic value ${intrinsic_value_per_share:.2f} capped at 5x current price ${current_price:.2f}")
                intrinsic_value_per_share = current_price * 5

            return {
                'symbol': self.symbol,
                'calculation_date': datetime.now().isoformat(),
                'intrinsic_value_per_share': intrinsic_value_per_share,
                'enterprise_value': enterprise_value,
                'equity_value': equity_value,
                'terminal_value': terminal_value,
                'pv_terminal_value': pv_terminal,
                'pv_projected_fcf': sum(pv_fcf),
                'wacc': wacc,
                'terminal_growth_rate': terminal_growth_rate,
                'projection_years': projection_years,
                'projected_fcf': projected_fcf,
                'present_value_fcf': pv_fcf,
                'shares_outstanding': shares_outstanding,
                'assumptions': {
                    'risk_free_rate': risk_free_rate,
                    'market_risk_premium': market_risk_premium,
                    'terminal_growth_rate': terminal_growth_rate,
                    'projection_years': projection_years
                }
            }

        except Exception as e:
            logger.error(f"DCF calculation failed for {self.symbol}: {e}")
            return {
                'symbol': self.symbol,
                'error': str(e),
                'intrinsic_value_per_share': None
            }

    def _calculate_wacc(self, risk_free_rate: float, market_risk_premium: float) -> float:
        """
        Calculate Weighted Average Cost of Capital (WACC)

        WACC = (E/V * Re) + (D/V * Rd * (1-T))
        """
        # Get financial data
        market_cap = self.data.get('market_cap', 0)
        total_debt = self.data.get('total_debt', 0)
        interest_expense = self.data.get('interest_expense', 0)
        beta = self.data.get('beta', 1.0)

        # Calculate cost of equity (CAPM)
        cost_of_equity = risk_free_rate + (beta * market_risk_premium)

        # Calculate cost of debt
        if total_debt > 0 and interest_expense > 0:
            cost_of_debt = abs(interest_expense) / total_debt
        else:
            cost_of_debt = risk_free_rate + 0.02  # Risk-free rate + credit spread

        # Calculate weights
        total_value = market_cap + total_debt
        if total_value > 0:
            equity_weight = market_cap / total_value
            debt_weight = total_debt / total_value
        else:
            equity_weight = 1.0
            debt_weight = 0.0

        # Tax rate estimation
        tax_rate = self._estimate_tax_rate()

        # Calculate WACC
        wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt * (1 - tax_rate))

        return max(wacc, 0.05)  # Minimum WACC of 5%

    def _project_free_cash_flows(self, years: int) -> List[float]:
        """
        Project future free cash flows with more conservative approach

        Args:
            years: Number of years to project

        Returns:
            List of projected FCF values
        """
        # Get base free cash flow
        base_fcf = self._calculate_current_fcf()

        # Estimate growth rate
        growth_rate = self._estimate_fcf_growth_rate()

        # More aggressive decay for high-growth companies
        projected_fcf = []
        for year in range(1, years + 1):
            # More aggressive decay: growth rate halves every 2 years
            decay_factor = 0.85 ** (year - 1)  # More aggressive decay
            adjusted_growth = growth_rate * decay_factor

            # Ensure growth doesn't go below long-term GDP growth
            adjusted_growth = max(adjusted_growth, 0.02)

            # Compound the growth
            if year == 1:
                fcf = base_fcf * (1 + adjusted_growth)
            else:
                fcf = projected_fcf[-1] * (1 + adjusted_growth)

            projected_fcf.append(fcf)

        return projected_fcf

    def _calculate_current_fcf(self) -> float:
        """Calculate current Free Cash Flow with sanity checks"""
        # Method 1: Direct FCF if available
        free_cash_flow = self.data.get('free_cash_flow')
        net_income = self.data.get('net_income', 0)
        revenue = self.data.get('revenue', 0)

        if free_cash_flow:
            # Sanity check: FCF shouldn't be more than 50% of revenue or 3x net income
            if revenue > 0 and free_cash_flow > revenue * 0.5:
                # Use more conservative estimate
                free_cash_flow = min(free_cash_flow, revenue * 0.3)

            if net_income > 0 and free_cash_flow > net_income * 3:
                # Use more conservative estimate
                free_cash_flow = min(free_cash_flow, net_income * 2)

            return free_cash_flow

        # Method 2: Operating Cash Flow - CapEx
        operating_cash_flow = self.data.get('operating_cash_flow')
        capital_expenditure = self.data.get('capital_expenditure', 0)

        if operating_cash_flow:
            fcf = operating_cash_flow - abs(capital_expenditure)
            # Apply same sanity checks
            if revenue > 0 and fcf > revenue * 0.5:
                fcf = min(fcf, revenue * 0.3)
            if net_income > 0 and fcf > net_income * 3:
                fcf = min(fcf, net_income * 2)
            return fcf

        # Method 3: Estimate from Net Income
        if net_income:
            # More conservative estimate: FCF ≈ Net Income * 0.8-1.5
            return net_income * 1.0  # Conservative 1x multiplier

        # Method 4: Estimate from Revenue
        if revenue:
            # Conservative estimate: FCF ≈ Revenue * 5-15% (use 8%)
            return revenue * 0.08

        return 0

    def _estimate_fcf_growth_rate(self) -> float:
        """Estimate FCF growth rate with realistic caps"""
        # Use earnings growth if available, but cap at reasonable levels
        earnings_growth = self.data.get('earnings_growth') or self.data.get('eps_growth')
        if earnings_growth and 0 < earnings_growth < 0.25:  # Cap at 25%
            return min(earnings_growth, 0.20)  # Max 20% for sustainability

        # Use revenue growth as proxy, but be more conservative
        revenue_growth = self.data.get('revenue_growth')
        if revenue_growth and 0 < revenue_growth < 0.4:  # More conservative range
            # FCF growth should be more conservative than revenue growth
            conservative_growth = revenue_growth * 0.5  # More conservative multiplier
            return min(conservative_growth, 0.15)  # Cap at 15%

        # For very high growth rates, use a much more conservative approach
        if earnings_growth and earnings_growth >= 0.25:
            # For high-growth companies, assume growth will normalize
            return 0.12  # Conservative 12% for high-growth companies

        if revenue_growth and revenue_growth >= 0.4:
            # For high revenue growth, be very conservative on FCF
            return 0.10  # Conservative 10% for high revenue growth

        # Default conservative growth
        return 0.05  # 5% default growth

    def _calculate_terminal_value(self, final_fcf: float, growth_rate: float, wacc: float) -> float:
        """
        Calculate terminal value using Gordon Growth Model

        Terminal Value = FCF(final year) * (1 + g) / (WACC - g)
        """
        if wacc <= growth_rate:
            # Adjust growth rate if it's too high
            growth_rate = wacc - 0.01

        terminal_fcf = final_fcf * (1 + growth_rate)
        terminal_value = terminal_fcf / (wacc - growth_rate)

        return terminal_value

    def _discount_cash_flows(self, cash_flows: List[float], discount_rate: float) -> List[float]:
        """
        Discount cash flows to present value

        Args:
            cash_flows: List of future cash flows
            discount_rate: Discount rate (WACC)

        Returns:
            List of present values
        """
        present_values = []
        for year, cf in enumerate(cash_flows, 1):
            pv = cf / ((1 + discount_rate) ** year)
            present_values.append(pv)

        return present_values

    def _calculate_equity_value(self, enterprise_value: float) -> float:
        """
        Calculate equity value from enterprise value

        Equity Value = Enterprise Value - Net Debt + Cash
        """
        total_debt = self.data.get('total_debt', 0)
        cash_and_equivalents = self.data.get('cash_and_equivalents', 0)

        net_debt = total_debt - cash_and_equivalents
        equity_value = enterprise_value - net_debt

        return max(equity_value, 0)  # Equity value can't be negative

    def _estimate_tax_rate(self) -> float:
        """Estimate effective tax rate"""
        # Try to calculate from financial data
        net_income = self.data.get('net_income')
        operating_income = self.data.get('operating_income')

        if net_income and operating_income and operating_income > 0:
            # Rough estimate
            tax_rate = 1 - (net_income / operating_income)
            return max(0, min(tax_rate, 0.4))  # Cap between 0 and 40%

        # Default corporate tax rate
        return 0.25

    def sensitivity_analysis(self,
                           wacc_range: tuple = (-0.01, 0.01, 0.005),
                           growth_range: tuple = (-0.01, 0.01, 0.005)) -> Dict[str, Any]:
        """
        Perform sensitivity analysis on DCF valuation

        Args:
            wacc_range: (min_change, max_change, step)
            growth_range: (min_change, max_change, step)

        Returns:
            Dictionary containing sensitivity analysis results
        """
        base_dcf = self.calculate_dcf_value()

        # Check if DCF calculation failed
        if 'error' in base_dcf or 'wacc' not in base_dcf:
            logger.warning(f"Cannot perform sensitivity analysis - base DCF failed: {base_dcf.get('error', 'Missing wacc')}")
            return {
                'base_intrinsic_value': None,
                'scenarios': [],
                'error': base_dcf.get('error', 'DCF calculation failed')
            }

        base_wacc = base_dcf['wacc']
        base_growth = base_dcf['terminal_growth_rate']

        results = []

        # Generate WACC and growth rate variations
        wacc_variations = np.arange(
            base_wacc + wacc_range[0],
            base_wacc + wacc_range[1] + wacc_range[2],
            wacc_range[2]
        )

        growth_variations = np.arange(
            base_growth + growth_range[0],
            base_growth + growth_range[1] + growth_range[2],
            growth_range[2]
        )

        for wacc in wacc_variations:
            for growth in growth_variations:
                if wacc > growth:  # Ensure WACC > growth rate
                    dcf_result = self.calculate_dcf_value(
                        terminal_growth_rate=growth,
                        risk_free_rate=0.03,  # Keep risk-free rate constant
                        market_risk_premium=wacc - base_wacc + 0.06  # Adjust market risk premium
                    )

                    results.append({
                        'wacc': wacc,
                        'terminal_growth': growth,
                        'intrinsic_value': dcf_result['intrinsic_value_per_share']
                    })

        # Create sensitivity matrix
        sensitivity_df = pd.DataFrame(results)

        return {
            'base_intrinsic_value': base_dcf['intrinsic_value_per_share'],
            'sensitivity_results': results,
            'min_value': sensitivity_df['intrinsic_value'].min() if not sensitivity_df.empty else None,
            'max_value': sensitivity_df['intrinsic_value'].max() if not sensitivity_df.empty else None,
            'mean_value': sensitivity_df['intrinsic_value'].mean() if not sensitivity_df.empty else None,
            'std_value': sensitivity_df['intrinsic_value'].std() if not sensitivity_df.empty else None
        }