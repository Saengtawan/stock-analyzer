"""
Sector Comparison and Benchmarking for SEC EDGAR Data
Provides comparative analysis across sectors and peer companies
"""
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger


class SectorComparison:
    """Compare insider/institutional activity across sectors"""

    def __init__(self):
        # Sample sector mappings (would be loaded from data source in production)
        self.sector_benchmarks = {
            'Technology': {
                'avg_insider_score': 6.8,
                'avg_institutional_score': 7.2,
                'avg_form4_filings': 45,
                'avg_form13f_filings': 8,
                'insider_activity_level': 'high',
                'institutional_interest': 'very_high'
            },
            'Healthcare': {
                'avg_insider_score': 6.2,
                'avg_institutional_score': 6.8,
                'avg_form4_filings': 35,
                'avg_form13f_filings': 6,
                'insider_activity_level': 'moderate',
                'institutional_interest': 'high'
            },
            'Financial': {
                'avg_insider_score': 5.8,
                'avg_institutional_score': 8.1,
                'avg_form4_filings': 28,
                'avg_form13f_filings': 12,
                'insider_activity_level': 'moderate',
                'institutional_interest': 'very_high'
            },
            'Consumer': {
                'avg_insider_score': 6.5,
                'avg_institutional_score': 6.9,
                'avg_form4_filings': 32,
                'avg_form13f_filings': 7,
                'insider_activity_level': 'moderate',
                'institutional_interest': 'high'
            },
            'Energy': {
                'avg_insider_score': 5.9,
                'avg_institutional_score': 6.0,
                'avg_form4_filings': 22,
                'avg_form13f_filings': 4,
                'insider_activity_level': 'low',
                'institutional_interest': 'moderate'
            },
            'Industrial': {
                'avg_insider_score': 6.1,
                'avg_institutional_score': 6.5,
                'avg_form4_filings': 26,
                'avg_form13f_filings': 5,
                'insider_activity_level': 'moderate',
                'institutional_interest': 'moderate'
            }
        }

    def get_sector_for_symbol(self, symbol: str) -> str:
        """Get sector for symbol (simplified mapping)"""
        # Simplified sector mapping
        tech_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'NFLX']
        healthcare_symbols = ['JNJ', 'PFE', 'UNH', 'ABBV', 'TMO', 'DHR', 'ABT']
        financial_symbols = ['JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'AXP']
        consumer_symbols = ['PG', 'KO', 'PEP', 'WMT', 'HD', 'MCD', 'NKE']
        energy_symbols = ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'PXD', 'MPC']
        industrial_symbols = ['BA', 'CAT', 'DE', 'UPS', 'HON', 'LMT', 'GE']

        if symbol in tech_symbols:
            return 'Technology'
        elif symbol in healthcare_symbols:
            return 'Healthcare'
        elif symbol in financial_symbols:
            return 'Financial'
        elif symbol in consumer_symbols:
            return 'Consumer'
        elif symbol in energy_symbols:
            return 'Energy'
        elif symbol in industrial_symbols:
            return 'Industrial'
        else:
            return 'Other'

    def compare_to_sector(self, symbol: str, sec_edgar_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compare company SEC EDGAR metrics to sector averages"""
        try:
            sector = self.get_sector_for_symbol(symbol)
            sector_benchmark = self.sector_benchmarks.get(sector, self.sector_benchmarks['Technology'])

            insider_data = sec_edgar_data.get('insider_trading', {})
            institutional_data = sec_edgar_data.get('institutional_ownership', {})

            # Extract current metrics
            current_insider_score = sec_edgar_data.get('insider_score', 5.0)
            current_institutional_score = sec_edgar_data.get('institutional_score', 5.0)
            current_form4_count = insider_data.get('form4_filings_count', 0)
            current_form13f_count = institutional_data.get('form13f_filings_count', 0)

            # Calculate percentiles
            insider_percentile = self._calculate_percentile(
                current_insider_score, sector_benchmark['avg_insider_score']
            )
            institutional_percentile = self._calculate_percentile(
                current_institutional_score, sector_benchmark['avg_institutional_score']
            )
            form4_percentile = self._calculate_percentile(
                current_form4_count, sector_benchmark['avg_form4_filings']
            )

            # Generate comparison insights
            comparison_insights = self._generate_comparison_insights(
                symbol, sector, current_insider_score, current_institutional_score,
                current_form4_count, sector_benchmark
            )

            return {
                'symbol': symbol,
                'sector': sector,
                'sector_comparison': {
                    'insider_score': {
                        'current': current_insider_score,
                        'sector_avg': sector_benchmark['avg_insider_score'],
                        'percentile': insider_percentile,
                        'performance': self._get_performance_rating(insider_percentile)
                    },
                    'institutional_score': {
                        'current': current_institutional_score,
                        'sector_avg': sector_benchmark['avg_institutional_score'],
                        'percentile': institutional_percentile,
                        'performance': self._get_performance_rating(institutional_percentile)
                    },
                    'form4_filings': {
                        'current': current_form4_count,
                        'sector_avg': sector_benchmark['avg_form4_filings'],
                        'percentile': form4_percentile,
                        'performance': self._get_performance_rating(form4_percentile)
                    },
                    'form13f_filings': {
                        'current': current_form13f_count,
                        'sector_avg': sector_benchmark['avg_form13f_filings'],
                        'relative_interest': self._compare_institutional_interest(
                            current_form13f_count, sector_benchmark['avg_form13f_filings']
                        )
                    }
                },
                'sector_ranking': {
                    'overall_percentile': (insider_percentile + institutional_percentile) / 2,
                    'insider_ranking': self._get_ranking_description(insider_percentile),
                    'institutional_ranking': self._get_ranking_description(institutional_percentile),
                    'activity_ranking': self._get_ranking_description(form4_percentile)
                },
                'comparison_insights': comparison_insights,
                'sector_context': {
                    'sector_characteristics': self._get_sector_characteristics(sector),
                    'typical_patterns': self._get_typical_patterns(sector)
                },
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in sector comparison: {e}")
            return {
                'symbol': symbol,
                'sector': 'Unknown',
                'error': 'Comparison analysis unavailable',
                'timestamp': datetime.now().isoformat()
            }

    def _calculate_percentile(self, current_value: float, sector_avg: float) -> float:
        """Calculate approximate percentile based on sector average"""
        if sector_avg == 0:
            return 50.0

        ratio = current_value / sector_avg

        # Simple percentile approximation
        if ratio >= 1.5:
            return 90.0
        elif ratio >= 1.2:
            return 75.0
        elif ratio >= 1.0:
            return 60.0
        elif ratio >= 0.8:
            return 40.0
        elif ratio >= 0.6:
            return 25.0
        else:
            return 10.0

    def _get_performance_rating(self, percentile: float) -> str:
        """Get performance rating from percentile"""
        if percentile >= 80:
            return 'excellent'
        elif percentile >= 60:
            return 'above_average'
        elif percentile >= 40:
            return 'average'
        elif percentile >= 20:
            return 'below_average'
        else:
            return 'poor'

    def _get_ranking_description(self, percentile: float) -> str:
        """Get ranking description from percentile"""
        if percentile >= 90:
            return 'Top 10%'
        elif percentile >= 75:
            return 'Top 25%'
        elif percentile >= 50:
            return 'Above Average'
        elif percentile >= 25:
            return 'Below Average'
        else:
            return 'Bottom 25%'

    def _compare_institutional_interest(self, current: int, sector_avg: float) -> str:
        """Compare institutional interest relative to sector"""
        if current == 0:
            return 'minimal'
        elif current >= sector_avg * 1.5:
            return 'very_high'
        elif current >= sector_avg:
            return 'above_average'
        elif current >= sector_avg * 0.5:
            return 'below_average'
        else:
            return 'low'

    def _generate_comparison_insights(self, symbol: str, sector: str,
                                    insider_score: float, institutional_score: float,
                                    form4_count: int, sector_benchmark: Dict[str, Any]) -> List[str]:
        """Generate sector comparison insights"""
        insights = []

        # Insider activity comparison
        if insider_score > sector_benchmark['avg_insider_score'] * 1.2:
            insights.append(f"🎯 {symbol} insider activity significantly above {sector} sector average")
        elif insider_score < sector_benchmark['avg_insider_score'] * 0.8:
            insights.append(f"📉 {symbol} insider activity below {sector} sector average")

        # Form 4 filings comparison
        if form4_count > sector_benchmark['avg_form4_filings'] * 1.5:
            insights.append(f"🔥 Exceptionally high Form 4 activity vs {sector} peers")
        elif form4_count == 0 and sector_benchmark['avg_form4_filings'] > 10:
            insights.append(f"😴 No insider activity while {sector} sector typically active")

        # Institutional interest comparison
        if institutional_score > sector_benchmark['avg_institutional_score'] * 1.2:
            insights.append(f"🏦 Strong institutional interest vs {sector} sector")
        elif institutional_score < sector_benchmark['avg_institutional_score'] * 0.8:
            insights.append(f"⚠️ Lower institutional interest than typical {sector} stock")

        # Sector-specific insights
        if sector == 'Technology' and insider_score > 7.0:
            insights.append("💻 High insider confidence typical of tech innovation cycles")
        elif sector == 'Financial' and institutional_score > 8.0:
            insights.append("🏦 Strong institutional presence typical of financial sector")

        return insights

    def _get_sector_characteristics(self, sector: str) -> Dict[str, str]:
        """Get sector-specific characteristics"""
        characteristics = {
            'Technology': {
                'insider_patterns': 'High activity during product cycles and earnings',
                'institutional_focus': 'Growth-oriented institutions prefer',
                'typical_drivers': 'Innovation, market expansion, acquisitions'
            },
            'Healthcare': {
                'insider_patterns': 'Activity around FDA approvals and clinical trials',
                'institutional_focus': 'Mixed growth and value institutions',
                'typical_drivers': 'Drug approvals, regulatory changes, demographics'
            },
            'Financial': {
                'insider_patterns': 'Moderate activity, regulatory constraints',
                'institutional_focus': 'Very high institutional ownership',
                'typical_drivers': 'Interest rates, regulations, economic cycles'
            },
            'Consumer': {
                'insider_patterns': 'Seasonal patterns, brand development',
                'institutional_focus': 'Steady institutional interest',
                'typical_drivers': 'Consumer trends, market share, margins'
            },
            'Energy': {
                'insider_patterns': 'Commodity price dependent activity',
                'institutional_focus': 'Cyclical institutional interest',
                'typical_drivers': 'Oil prices, regulations, ESG concerns'
            },
            'Industrial': {
                'insider_patterns': 'Economic cycle dependent',
                'institutional_focus': 'Value-oriented institutions',
                'typical_drivers': 'Economic growth, infrastructure, trade'
            }
        }

        return characteristics.get(sector, characteristics['Technology'])

    def _get_typical_patterns(self, sector: str) -> List[str]:
        """Get typical insider/institutional patterns for sector"""
        patterns = {
            'Technology': [
                "Insider buying often precedes product announcements",
                "High institutional turnover during growth phases",
                "Seasonal patterns around quarterly earnings"
            ],
            'Healthcare': [
                "Insider activity spikes around clinical trial results",
                "Long-term institutional holdings common",
                "Regulatory news drives activity"
            ],
            'Financial': [
                "Regulatory restrictions limit insider activity",
                "Institutional ownership typically 70%+",
                "Interest rate sensitivity affects flows"
            ],
            'Consumer': [
                "Brand strength correlates with institutional interest",
                "Seasonal insider activity patterns",
                "Defensive characteristics attract institutions"
            ],
            'Energy': [
                "Commodity price cycles drive activity",
                "ESG concerns affect institutional flows",
                "Cyclical institutional interest"
            ],
            'Industrial': [
                "Economic indicators drive insider confidence",
                "Infrastructure spending affects institutional interest",
                "Trade policy sensitivity"
            ]
        }

        return patterns.get(sector, patterns['Technology'])