"""
SEC EDGAR Client - Real API Implementation
Uses the official SEC EDGAR API with proper User-Agent headers
"""
import requests
import json
import time
from typing import Dict, Any, Optional
from loguru import logger


class SECEdgarClient:
    """SEC EDGAR API client with proper headers"""

    def __init__(self):
        self.base_url = "https://data.sec.gov"
        self.tickers_url = "https://www.sec.gov"
        self.headers = {
            'User-Agent': 'Stock-Analyzer saengtawan239.1@hotmail.com',
            'Accept-Encoding': 'gzip, deflate'
        }
        self.company_tickers = {}
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Rate limiting - SEC allows ~10 requests/second
        self.last_request_time = 0
        self.min_interval = 0.1  # 100ms between requests

    def _rate_limit(self):
        """Ensure we don't exceed SEC rate limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_interval:
            time.sleep(self.min_interval - time_since_last)
        self.last_request_time = time.time()

    def _load_company_tickers(self):
        """Load company tickers from SEC API"""
        if self.company_tickers:
            return self.company_tickers

        try:
            self._rate_limit()
            url = f"{self.tickers_url}/files/company_tickers.json"
            logger.info(f"Loading company tickers from {url}")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Convert to ticker -> CIK mapping
            for entry in data.values():
                if isinstance(entry, dict) and 'ticker' in entry and 'cik_str' in entry:
                    ticker = entry['ticker'].upper()
                    cik = str(entry['cik_str']).zfill(10)  # Pad with zeros
                    self.company_tickers[ticker] = cik

            logger.info(f"Loaded {len(self.company_tickers)} company tickers from SEC")
            return self.company_tickers

        except Exception as e:
            logger.warning(f"Failed to load company tickers: {e}")
            return {}

    def get_cik_from_ticker(self, ticker: str) -> Optional[str]:
        """Get CIK (Central Index Key) from ticker symbol"""
        if not self.company_tickers:
            self._load_company_tickers()

        cik = self.company_tickers.get(ticker.upper())
        if cik:
            logger.debug(f"Found CIK {cik} for ticker {ticker}")
            return cik
        else:
            logger.debug(f"CIK not found for ticker {ticker}")
            return None

    def get_company_submissions(self, cik: str) -> Dict[str, Any]:
        """Get company submissions data from SEC"""
        try:
            self._rate_limit()
            # Ensure CIK is 10 digits with leading zeros
            cik_padded = str(cik).zfill(10)
            url = f"{self.base_url}/submissions/CIK{cik_padded}.json"

            logger.debug(f"Fetching submissions for CIK {cik_padded}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Error fetching submissions for CIK {cik}: {e}")
            return {}

    def get_insider_transactions(self, cik: str) -> Dict[str, Any]:
        """Get enhanced insider transaction data with trend analysis"""
        submissions = self.get_company_submissions(cik)

        if not submissions:
            return {
                'recent_transactions': [],
                'insider_sentiment': 'neutral',
                'total_transactions': 0,
                'net_insider_activity': 0,
                'has_real_data': False,
                'trend_analysis': {},
                'confidence_score': 5.0,
                'risk_alerts': []
            }

        # Look for Form 4 filings (insider transactions)
        filings = submissions.get('filings', {}).get('recent', {})
        forms = filings.get('form', [])
        filing_dates = filings.get('filingDate', [])

        form4_indices = [i for i, form in enumerate(forms) if form == '4']
        form4_count = len(form4_indices)

        # Enhanced analysis
        trend_analysis = self._analyze_insider_trends(forms, filing_dates)
        confidence_score = self._calculate_insider_confidence(form4_count, trend_analysis)
        risk_alerts = self._generate_insider_alerts(form4_count, trend_analysis)

        sentiment = self._determine_insider_sentiment(form4_count, trend_analysis)

        return {
            'recent_transactions': [],  # Would need detailed parsing
            'insider_sentiment': sentiment,
            'total_transactions': form4_count,
            'net_insider_activity': 0,  # Would need detailed analysis
            'has_real_data': True,
            'form4_filings_count': form4_count,
            'trend_analysis': trend_analysis,
            'confidence_score': confidence_score,
            'risk_alerts': risk_alerts,
            'filing_distribution': self._get_filing_distribution(form4_indices, filing_dates)
        }

    def get_institutional_ownership(self, cik: str) -> Dict[str, Any]:
        """Get enhanced institutional ownership data with flow analysis"""
        submissions = self.get_company_submissions(cik)

        if not submissions:
            return {
                'total_shares_held': 0,
                'ownership_percentage': 0,
                'top_institutions': [],
                'recent_changes': [],
                'has_real_data': False,
                'flow_analysis': {},
                'smart_money_score': 5.0,
                'institutional_alerts': []
            }

        # Look for 13F filings (institutional ownership)
        filings = submissions.get('filings', {}).get('recent', {})
        forms = filings.get('form', [])
        filing_dates = filings.get('filingDate', [])

        form13f_count = sum(1 for form in forms if '13F' in form)

        # Enhanced institutional analysis
        flow_analysis = self._analyze_institutional_flow(forms, filing_dates)
        smart_money_score = self._calculate_smart_money_score(form13f_count, flow_analysis)
        institutional_alerts = self._generate_institutional_alerts(form13f_count, flow_analysis)

        return {
            'total_shares_held': 0,  # Would need detailed parsing
            'ownership_percentage': 0,  # Would need detailed analysis
            'top_institutions': [],  # Would need detailed parsing
            'recent_changes': [],  # Would need detailed analysis
            'has_real_data': True,
            'form13f_filings_count': form13f_count,
            'flow_analysis': flow_analysis,
            'smart_money_score': smart_money_score,
            'institutional_alerts': institutional_alerts,
            'filing_trend': self._get_institutional_trend(forms, filing_dates)
        }

    def _analyze_insider_trends(self, forms: list, filing_dates: list) -> Dict[str, Any]:
        """Analyze insider trading trends over time"""
        from datetime import datetime, timedelta
        import calendar

        if not forms or not filing_dates:
            return {
                'monthly_distribution': {},
                'recent_activity_level': 'unknown',
                'trend_direction': 'neutral',
                'activity_spike': False
            }

        try:
            # Get Form 4 indices with dates
            form4_data = []
            for i, (form, date_str) in enumerate(zip(forms, filing_dates)):
                if form == '4' and date_str:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        form4_data.append(date_obj)
                    except:
                        continue

            if not form4_data:
                return {
                    'monthly_distribution': {},
                    'recent_activity_level': 'none',
                    'trend_direction': 'neutral',
                    'activity_spike': False
                }

            # Monthly distribution
            monthly_counts = {}
            now = datetime.now()
            for date_obj in form4_data:
                month_key = f"{date_obj.year}-{date_obj.month:02d}"
                monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1

            # Recent activity (last 3 months)
            three_months_ago = now - timedelta(days=90)
            recent_count = sum(1 for date_obj in form4_data if date_obj >= three_months_ago)

            # Activity level classification
            if recent_count == 0:
                activity_level = 'none'
            elif recent_count <= 5:
                activity_level = 'low'
            elif recent_count <= 15:
                activity_level = 'moderate'
            elif recent_count <= 30:
                activity_level = 'high'
            else:
                activity_level = 'very_high'

            # Trend direction (comparing last 3 vs previous 3 months)
            six_months_ago = now - timedelta(days=180)
            last_3_months = sum(1 for date_obj in form4_data if date_obj >= three_months_ago)
            prev_3_months = sum(1 for date_obj in form4_data if six_months_ago <= date_obj < three_months_ago)

            if prev_3_months == 0:
                trend_direction = 'new_activity' if last_3_months > 0 else 'neutral'
            else:
                ratio = last_3_months / prev_3_months
                if ratio > 1.5:
                    trend_direction = 'increasing'
                elif ratio < 0.7:
                    trend_direction = 'decreasing'
                else:
                    trend_direction = 'stable'

            # Activity spike detection
            activity_spike = recent_count > 20 or (prev_3_months > 0 and last_3_months / prev_3_months > 2)

            return {
                'monthly_distribution': monthly_counts,
                'recent_activity_level': activity_level,
                'trend_direction': trend_direction,
                'activity_spike': activity_spike,
                'recent_count': recent_count,
                'total_analyzed': len(form4_data)
            }

        except Exception as e:
            logger.error(f"Error analyzing insider trends: {e}")
            return {
                'monthly_distribution': {},
                'recent_activity_level': 'unknown',
                'trend_direction': 'neutral',
                'activity_spike': False
            }

    def _calculate_insider_confidence(self, form4_count: int, trend_analysis: Dict[str, Any]) -> float:
        """Calculate insider confidence score with enhanced factors"""
        base_score = 5.0

        # Activity level scoring
        activity_level = trend_analysis.get('recent_activity_level', 'none')
        activity_scores = {
            'none': 4.0,
            'low': 5.5,
            'moderate': 6.5,
            'high': 7.5,
            'very_high': 8.5
        }

        activity_score = activity_scores.get(activity_level, 5.0)

        # Trend direction modifier
        trend_direction = trend_analysis.get('trend_direction', 'neutral')
        trend_modifiers = {
            'increasing': 1.2,
            'stable': 1.0,
            'decreasing': 0.8,
            'new_activity': 1.1,
            'neutral': 1.0
        }

        trend_modifier = trend_modifiers.get(trend_direction, 1.0)

        # Activity spike bonus
        spike_bonus = 0.5 if trend_analysis.get('activity_spike', False) else 0

        # Calculate final score
        final_score = (activity_score * trend_modifier) + spike_bonus

        # Ensure score is within bounds
        return max(1.0, min(10.0, final_score))

    def _generate_insider_alerts(self, form4_count: int, trend_analysis: Dict[str, Any]) -> list:
        """Generate insider trading alerts"""
        alerts = []

        activity_level = trend_analysis.get('recent_activity_level', 'none')
        trend_direction = trend_analysis.get('trend_direction', 'neutral')
        activity_spike = trend_analysis.get('activity_spike', False)

        if activity_spike:
            alerts.append({
                'type': 'high_activity',
                'severity': 'warning',
                'message': 'Insider activity spike detected - แนะนำติดตามอย่างใกล้ชิด',
                'recommendation': 'Monitor for potential price movements'
            })

        if activity_level == 'very_high':
            alerts.append({
                'type': 'very_high_activity',
                'severity': 'info',
                'message': 'Very high insider activity - อาจมีข่าวสำคัญเกิดขึ้น',
                'recommendation': 'Check for upcoming announcements'
            })

        if trend_direction == 'increasing':
            alerts.append({
                'type': 'increasing_trend',
                'severity': 'info',
                'message': 'Insider activity trending upward - สัญญาณเชิงบวก',
                'recommendation': 'Positive signal for company outlook'
            })
        elif trend_direction == 'decreasing':
            alerts.append({
                'type': 'decreasing_trend',
                'severity': 'caution',
                'message': 'Insider activity decreasing - ควรระวัง',
                'recommendation': 'Monitor for potential negative news'
            })

        return alerts

    def _determine_insider_sentiment(self, form4_count: int, trend_analysis: Dict[str, Any]) -> str:
        """Determine overall insider sentiment"""
        activity_level = trend_analysis.get('recent_activity_level', 'none')
        trend_direction = trend_analysis.get('trend_direction', 'neutral')

        if activity_level in ['high', 'very_high'] and trend_direction == 'increasing':
            return 'very_active'
        elif activity_level in ['moderate', 'high']:
            return 'active'
        elif activity_level == 'low':
            return 'quiet'
        elif activity_level == 'none':
            return 'neutral'
        else:
            return 'neutral'

    def _get_filing_distribution(self, form4_indices: list, filing_dates: list) -> Dict[str, Any]:
        """Get distribution of Form 4 filings by time period"""
        from datetime import datetime, timedelta

        if not form4_indices or not filing_dates:
            return {
                'last_30_days': 0,
                'last_90_days': 0,
                'last_180_days': 0,
                'older': 0
            }

        now = datetime.now()
        distribution = {
            'last_30_days': 0,
            'last_90_days': 0,
            'last_180_days': 0,
            'older': 0
        }

        for idx in form4_indices:
            if idx < len(filing_dates):
                try:
                    filing_date = datetime.strptime(filing_dates[idx], '%Y-%m-%d')
                    days_ago = (now - filing_date).days

                    if days_ago <= 30:
                        distribution['last_30_days'] += 1
                    elif days_ago <= 90:
                        distribution['last_90_days'] += 1
                    elif days_ago <= 180:
                        distribution['last_180_days'] += 1
                    else:
                        distribution['older'] += 1
                except:
                    distribution['older'] += 1

        return distribution

    def _analyze_institutional_flow(self, forms: list, filing_dates: list) -> Dict[str, Any]:
        """Analyze institutional money flow trends"""
        from datetime import datetime, timedelta

        if not forms or not filing_dates:
            return {
                'flow_direction': 'neutral',
                'activity_trend': 'stable',
                'smart_money_signal': 'neutral'
            }

        try:
            # Find 13F filings with dates
            institutional_filings = []
            for i, (form, date_str) in enumerate(zip(forms, filing_dates)):
                if '13F' in form and date_str:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        institutional_filings.append(date_obj)
                    except:
                        continue

            if not institutional_filings:
                return {
                    'flow_direction': 'unknown',
                    'activity_trend': 'no_data',
                    'smart_money_signal': 'neutral'
                }

            # Analyze recent vs historical
            now = datetime.now()
            six_months_ago = now - timedelta(days=180)
            three_months_ago = now - timedelta(days=90)

            recent_filings = [d for d in institutional_filings if d >= three_months_ago]
            historical_filings = [d for d in institutional_filings if six_months_ago <= d < three_months_ago]

            recent_count = len(recent_filings)
            historical_count = len(historical_filings)

            # Determine flow direction
            if historical_count == 0:
                flow_direction = 'new_interest' if recent_count > 0 else 'neutral'
            else:
                ratio = recent_count / historical_count
                if ratio > 1.3:
                    flow_direction = 'increasing'
                elif ratio < 0.7:
                    flow_direction = 'decreasing'
                else:
                    flow_direction = 'stable'

            # Activity trend
            if recent_count == 0:
                activity_trend = 'dormant'
            elif recent_count <= 2:
                activity_trend = 'low'
            elif recent_count <= 5:
                activity_trend = 'moderate'
            else:
                activity_trend = 'high'

            # Smart money signal
            if flow_direction == 'increasing' and activity_trend in ['moderate', 'high']:
                smart_money_signal = 'bullish'
            elif flow_direction == 'decreasing':
                smart_money_signal = 'bearish'
            else:
                smart_money_signal = 'neutral'

            return {
                'flow_direction': flow_direction,
                'activity_trend': activity_trend,
                'smart_money_signal': smart_money_signal,
                'recent_count': recent_count,
                'historical_count': historical_count
            }

        except Exception as e:
            logger.error(f"Error analyzing institutional flow: {e}")
            return {
                'flow_direction': 'unknown',
                'activity_trend': 'error',
                'smart_money_signal': 'neutral'
            }

    def _calculate_smart_money_score(self, form13f_count: int, flow_analysis: Dict[str, Any]) -> float:
        """Calculate smart money confidence score"""
        base_score = 5.0

        # Activity level scoring
        activity_trend = flow_analysis.get('activity_trend', 'low')
        activity_scores = {
            'dormant': 3.0,
            'low': 4.0,
            'moderate': 6.0,
            'high': 7.5
        }

        activity_score = activity_scores.get(activity_trend, 5.0)

        # Flow direction modifier
        flow_direction = flow_analysis.get('flow_direction', 'neutral')
        flow_modifiers = {
            'increasing': 1.3,
            'stable': 1.0,
            'decreasing': 0.7,
            'new_interest': 1.1,
            'neutral': 1.0
        }

        flow_modifier = flow_modifiers.get(flow_direction, 1.0)

        # Smart money signal bonus
        smart_signal = flow_analysis.get('smart_money_signal', 'neutral')
        signal_bonuses = {
            'bullish': 1.0,
            'neutral': 0.0,
            'bearish': -1.0
        }

        signal_bonus = signal_bonuses.get(smart_signal, 0.0)

        # Calculate final score
        final_score = (activity_score * flow_modifier) + signal_bonus

        return max(1.0, min(10.0, final_score))

    def _generate_institutional_alerts(self, form13f_count: int, flow_analysis: Dict[str, Any]) -> list:
        """Generate institutional activity alerts"""
        alerts = []

        flow_direction = flow_analysis.get('flow_direction', 'neutral')
        smart_signal = flow_analysis.get('smart_money_signal', 'neutral')
        activity_trend = flow_analysis.get('activity_trend', 'low')

        if smart_signal == 'bullish':
            alerts.append({
                'type': 'bullish_institutions',
                'severity': 'positive',
                'message': 'Smart money showing bullish signals - สถาบันเพิ่มการลงทุน',
                'recommendation': 'Institutional interest increasing'
            })
        elif smart_signal == 'bearish':
            alerts.append({
                'type': 'bearish_institutions',
                'severity': 'warning',
                'message': 'Institutional interest declining - สถาบันลดการลงทุน',
                'recommendation': 'Monitor for continued outflow'
            })

        if activity_trend == 'high':
            alerts.append({
                'type': 'high_institutional_activity',
                'severity': 'info',
                'message': 'High institutional activity detected - กิจกรรมสถาบันสูง',
                'recommendation': 'Monitor for significant position changes'
            })
        elif activity_trend == 'dormant':
            alerts.append({
                'type': 'low_institutional_interest',
                'severity': 'neutral',
                'message': 'Low institutional interest - สถาบันให้ความสนใจน้อย',
                'recommendation': 'May indicate lack of institutional coverage'
            })

        return alerts

    def _get_institutional_trend(self, forms: list, filing_dates: list) -> Dict[str, Any]:
        """Get institutional filing trend over time"""
        from datetime import datetime, timedelta

        if not forms or not filing_dates:
            return {
                'quarterly_trend': 'stable',
                'recent_momentum': 'neutral',
                'filing_frequency': 'unknown'
            }

        try:
            # Count 13F filings by quarter
            quarterly_counts = {}
            now = datetime.now()

            for form, date_str in zip(forms, filing_dates):
                if '13F' in form and date_str:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        quarter = f"{date_obj.year}-Q{((date_obj.month-1)//3)+1}"
                        quarterly_counts[quarter] = quarterly_counts.get(quarter, 0) + 1
                    except:
                        continue

            # Analyze trend
            if len(quarterly_counts) < 2:
                quarterly_trend = 'insufficient_data'
                recent_momentum = 'neutral'
            else:
                sorted_quarters = sorted(quarterly_counts.keys())
                recent_quarters = sorted_quarters[-2:]

                if len(recent_quarters) == 2:
                    recent_change = quarterly_counts[recent_quarters[1]] - quarterly_counts[recent_quarters[0]]
                    if recent_change > 0:
                        quarterly_trend = 'increasing'
                        recent_momentum = 'positive'
                    elif recent_change < 0:
                        quarterly_trend = 'decreasing'
                        recent_momentum = 'negative'
                    else:
                        quarterly_trend = 'stable'
                        recent_momentum = 'neutral'
                else:
                    quarterly_trend = 'stable'
                    recent_momentum = 'neutral'

            # Filing frequency
            total_13f = sum(quarterly_counts.values()) if quarterly_counts else 0
            if total_13f == 0:
                filing_frequency = 'none'
            elif total_13f <= 2:
                filing_frequency = 'low'
            elif total_13f <= 5:
                filing_frequency = 'moderate'
            else:
                filing_frequency = 'high'

            return {
                'quarterly_trend': quarterly_trend,
                'recent_momentum': recent_momentum,
                'filing_frequency': filing_frequency,
                'total_13f_filings': total_13f
            }

        except Exception as e:
            logger.error(f"Error analyzing institutional trend: {e}")
            return {
                'quarterly_trend': 'unknown',
                'recent_momentum': 'neutral',
                'filing_frequency': 'unknown'
            }