"""
Enhanced Yahoo Finance Client - Real Data Only
Provides earnings and analyst data from Yahoo Finance
"""
import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger


class YahooEnhancedClient:
    """Enhanced Yahoo Finance client for real earnings and analyst data"""

    def __init__(self):
        """Initialize Yahoo Enhanced Client"""
        self.name = "Yahoo Enhanced Client"

    def get_earnings_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get real earnings data from Yahoo Finance
        Args:
            symbol: Stock symbol
        Returns:
            Dictionary with earnings analysis
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get company info for current price and financials
            info = ticker.info
            current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))

            # Get quarterly financials instead of deprecated earnings
            quarterly_financials = None
            try:
                quarterly_financials = ticker.quarterly_financials
            except Exception as e:
                logger.warning(f"Could not get quarterly financials for {symbol}: {e}")

            # Get income statement for EPS data
            income_stmt = None
            try:
                income_stmt = ticker.income_stmt
            except Exception as e:
                logger.warning(f"Could not get income statement for {symbol}: {e}")

            # Calculate earnings metrics from available data
            earnings_analysis = {}

            if quarterly_financials is not None and not quarterly_financials.empty:
                # Get recent quarters
                recent_quarters = quarterly_financials.head(4)  # Last 4 quarters

                # Calculate revenue growth
                if len(recent_quarters.columns) >= 2:
                    try:
                        revenue_col = None
                        for col in ['Total Revenue', 'Revenue', 'Net Sales']:
                            if col in recent_quarters.index:
                                revenue_col = col
                                break

                        if revenue_col:
                            current_revenue = recent_quarters.loc[revenue_col].iloc[0]
                            prev_revenue = recent_quarters.loc[revenue_col].iloc[1]

                            if prev_revenue != 0:
                                revenue_growth = ((current_revenue - prev_revenue) / prev_revenue) * 100
                                earnings_analysis['revenue_growth'] = revenue_growth
                    except Exception as e:
                        logger.debug(f"Could not calculate revenue growth: {e}")

            # Get EPS data from info
            eps_current = info.get('trailingEps', 0)
            eps_forward = info.get('forwardEps', 0)

            earnings_analysis.update({
                'symbol': symbol,
                'current_eps': eps_current,
                'forward_eps': eps_forward,
                'has_earnings_data': quarterly_financials is not None,
                'next_earnings_date': info.get('earningsDate', None),
                'earnings_score': 7 if eps_current > 0 else 3  # Simple scoring
            })

            return earnings_analysis

        except Exception as e:
            logger.error(f"Error getting earnings data for {symbol}: {e}")
            return {
                'symbol': symbol,
                'error': 'ไม่สามารถดึงข้อมูล earnings ได้',
                'has_earnings_data': False,
                'earnings_score': 0
            }

    def get_analyst_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get real analyst data from Yahoo Finance
        Args:
            symbol: Stock symbol
        Returns:
            Dictionary with analyst analysis
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Get analyst targets
            target_mean = info.get('targetMeanPrice', 0)
            target_high = info.get('targetHighPrice', 0)
            target_low = info.get('targetLowPrice', 0)
            current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))

            # Get recommendation
            recommendation_key = info.get('recommendationKey', 'hold')
            num_analysts = info.get('numberOfAnalystOpinions', 0)

            # Calculate upside potential
            upside_potential = 0
            if current_price > 0 and target_mean > 0:
                upside_potential = ((target_mean - current_price) / current_price) * 100

            # Get recommendations breakdown
            recommendations = None
            try:
                recommendations = ticker.recommendations
            except Exception as e:
                logger.warning(f"Could not get recommendations for {symbol}: {e}")

            # Analyze recommendations if available
            rec_summary = {'buy': 0, 'hold': 0, 'sell': 0}
            if recommendations is not None and not recommendations.empty:
                try:
                    # Use the most recent recommendations data
                    latest_rec = recommendations.iloc[-1]  # Most recent row

                    # Extract numerical data from Yahoo Finance format
                    strong_buy = latest_rec.get('strongBuy', 0) or 0
                    buy = latest_rec.get('buy', 0) or 0
                    hold = latest_rec.get('hold', 0) or 0
                    sell = latest_rec.get('sell', 0) or 0
                    strong_sell = latest_rec.get('strongSell', 0) or 0

                    # Combine buy categories and sell categories
                    rec_summary = {
                        'buy': int(strong_buy + buy),
                        'hold': int(hold),
                        'sell': int(sell + strong_sell)
                    }

                    logger.info(f"Extracted recommendations for {symbol}: {rec_summary}")

                except Exception as e:
                    logger.debug(f"Could not analyze recommendations: {e}")

            # Calculate consensus score
            total_recs = sum(rec_summary.values())
            consensus_score = 5  # Default neutral
            if total_recs > 0:
                buy_pct = rec_summary['buy'] / total_recs
                sell_pct = rec_summary['sell'] / total_recs
                consensus_score = 1 + (buy_pct * 8) - (sell_pct * 4)  # 1-9 scale
                consensus_score = max(1, min(9, consensus_score))

            return {
                'symbol': symbol,
                'avg_price_target': target_mean,
                'high_target': target_high,
                'low_target': target_low,
                'current_price': current_price,
                'upside_potential': upside_potential,
                'recommendation': recommendation_key,
                'num_analysts': num_analysts,
                'consensus_score': consensus_score,
                'recommendations_breakdown': rec_summary,
                'has_analyst_data': target_mean > 0 or num_analysts > 0
            }

        except Exception as e:
            logger.error(f"Error getting analyst data for {symbol}: {e}")
            return {
                'symbol': symbol,
                'error': 'ไม่สามารถดึงข้อมูล analyst ได้',
                'has_analyst_data': False,
                'consensus_score': 5
            }

    def get_comprehensive_analysis(self, symbol: str) -> Dict[str, Any]:
        """
        Get comprehensive analysis combining earnings and analyst data
        Args:
            symbol: Stock symbol
        Returns:
            Complete analysis dictionary
        """
        logger.info(f"Getting comprehensive Yahoo Finance analysis for {symbol}")

        earnings_data = self.get_earnings_data(symbol)
        analyst_data = self.get_analyst_data(symbol)

        # Combine data
        combined_score = (
            earnings_data.get('earnings_score', 0) * 0.6 +
            analyst_data.get('consensus_score', 5) * 0.4
        )

        return {
            'symbol': symbol,
            'earnings_analysis': earnings_data,
            'analyst_coverage': analyst_data,
            'combined_score': combined_score,
            'data_quality': 'real' if (earnings_data.get('has_earnings_data') or analyst_data.get('has_analyst_data')) else 'limited',
            'timestamp': datetime.now().isoformat()
        }


# Test function
def test_yahoo_enhanced():
    """Test the Yahoo Enhanced Client"""
    client = YahooEnhancedClient()

    # Test with AAPL
    print("Testing AAPL...")
    result = client.get_comprehensive_analysis('AAPL')

    print(f"Symbol: {result['symbol']}")
    print(f"Data quality: {result['data_quality']}")
    print(f"Combined score: {result['combined_score']:.1f}")

    earnings = result['earnings_analysis']
    print(f"Current EPS: {earnings.get('current_eps', 'N/A')}")
    print(f"Forward EPS: {earnings.get('forward_eps', 'N/A')}")

    analyst = result['analyst_coverage']
    print(f"Target price: ${analyst.get('avg_price_target', 0):.2f}")
    print(f"Upside potential: {analyst.get('upside_potential', 0):.1f}%")
    print(f"Recommendation: {analyst.get('recommendation', 'N/A')}")
    print(f"Number of analysts: {analyst.get('num_analysts', 0)}")


if __name__ == "__main__":
    test_yahoo_enhanced()