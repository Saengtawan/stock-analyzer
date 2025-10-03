"""
Insider and Institutional Analysis - Real SEC EDGAR Data
Uses the official SEC EDGAR API to get real insider trading and institutional data
"""
from typing import Dict, Any
from datetime import datetime
from loguru import logger
from api.sec_edgar_client import SECEdgarClient
from analysis.sector_comparison import SectorComparison


class InsiderInstitutionalAnalyzer:
    """Real insider and institutional analyzer using SEC EDGAR"""

    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self.sec_client = SECEdgarClient()
        self.sector_comparison = SectorComparison()

    def get_comprehensive_analysis(self) -> Dict[str, Any]:
        """Get real insider and institutional analysis from SEC EDGAR"""
        logger.info(f"Analyzing insider/institutional activity for {self.symbol}")

        # Get CIK for the symbol
        cik = self.sec_client.get_cik_from_ticker(self.symbol)

        if not cik:
            logger.warning(f"No SEC EDGAR CIK found for {self.symbol}")
            return self._get_fallback_data()

        # Get insider and institutional data
        insider_data = self.get_insider_transactions(cik)
        institutional_data = self.get_institutional_ownership(cik)

        # Calculate scores based on real data
        insider_score = self._calculate_insider_score(insider_data)
        institutional_score = self._calculate_institutional_score(institutional_data)
        combined_score = (insider_score + institutional_score) / 2

        # Generate insights
        insights = self._generate_insights(insider_data, institutional_data)

        # Add sector comparison
        sector_analysis = self.sector_comparison.compare_to_sector(self.symbol, {
            'insider_trading': insider_data,
            'institutional_ownership': institutional_data,
            'insider_score': insider_score,
            'institutional_score': institutional_score,
            'combined_score': combined_score
        })

        return {
            'symbol': self.symbol,
            'cik': cik,
            'insider_trading': insider_data,
            'institutional_ownership': institutional_data,
            'insider_score': insider_score,
            'institutional_score': institutional_score,
            'combined_score': combined_score,
            'key_insights': insights,
            'sector_analysis': sector_analysis,
            'data_quality': 'real_sec_edgar',
            'timestamp': datetime.now().isoformat(),
            'has_real_data': True
        }

    def get_insider_transactions(self, cik: str = None) -> Dict[str, Any]:
        """Get real insider transaction data from SEC EDGAR"""
        if not cik:
            cik = self.sec_client.get_cik_from_ticker(self.symbol)
            if not cik:
                logger.warning(f"No SEC EDGAR insider data found for {self.symbol}")
                return {
                    'recent_transactions': [],
                    'insider_sentiment': 'unknown',
                    'total_transactions': 0,
                    'net_insider_activity': 0,
                    'has_real_data': False
                }

        return self.sec_client.get_insider_transactions(cik)

    def get_institutional_ownership(self, cik: str = None) -> Dict[str, Any]:
        """Get real institutional ownership data from SEC EDGAR"""
        if not cik:
            cik = self.sec_client.get_cik_from_ticker(self.symbol)
            if not cik:
                logger.warning(f"No SEC EDGAR institutional data found for {self.symbol}")
                return {
                    'total_shares_held': 0,
                    'ownership_percentage': 0,
                    'top_institutions': [],
                    'recent_changes': [],
                    'has_real_data': False
                }

        return self.sec_client.get_institutional_ownership(cik)

    def _calculate_insider_score(self, insider_data: Dict[str, Any]) -> float:
        """Calculate insider activity score (1-10)"""
        if not insider_data.get('has_real_data'):
            return 5.0  # Neutral when no data

        form4_count = insider_data.get('form4_filings_count', 0)

        # Score based on insider activity level
        if form4_count == 0:
            return 5.0  # Neutral - no recent insider activity
        elif form4_count <= 2:
            return 6.0  # Slight positive - some activity
        elif form4_count <= 5:
            return 7.0  # Positive - moderate activity
        else:
            return 8.0  # Strong positive - high activity

    def _calculate_institutional_score(self, institutional_data: Dict[str, Any]) -> float:
        """Calculate institutional interest score (1-10)"""
        if not institutional_data.get('has_real_data'):
            return 5.0  # Neutral when no data

        form13f_count = institutional_data.get('form13f_filings_count', 0)

        # Score based on institutional filing activity
        if form13f_count == 0:
            return 4.0  # Slightly negative - no institutional interest
        elif form13f_count <= 2:
            return 6.0  # Positive - some institutional interest
        else:
            return 7.0  # Strong positive - high institutional interest

    def _generate_insights(self, insider_data: Dict[str, Any], institutional_data: Dict[str, Any]) -> list:
        """Generate enhanced key insights from real SEC data"""
        insights = []

        # Enhanced insider insights
        form4_count = insider_data.get('form4_filings_count', 0)
        trend_analysis = insider_data.get('trend_analysis', {})
        activity_level = trend_analysis.get('recent_activity_level', 'none')
        trend_direction = trend_analysis.get('trend_direction', 'neutral')

        if form4_count > 0:
            if activity_level == 'very_high':
                insights.append(f"🔥 Very High Insider Activity: {form4_count} Form 4 filings - กิจกรรม insider สูงมาก")
            elif activity_level == 'high':
                insights.append(f"⚡ High Insider Activity: {form4_count} Form 4 filings - กิจกรรม insider สูง")
            elif trend_direction == 'increasing':
                insights.append(f"📈 Increasing Insider Trend: {form4_count} Form 4 filings - แนวโน้มเพิ่มขึ้น")
            else:
                insights.append(f"📋 Insider Activity: {form4_count} Form 4 filings - มีกิจกรรม insider trading")
        else:
            insights.append("😴 No Recent Insider Activity - ไม่มีกิจกรรม insider trading ล่าสุด")

        # Enhanced institutional insights
        form13f_count = institutional_data.get('form13f_filings_count', 0)
        flow_analysis = institutional_data.get('flow_analysis', {})
        smart_signal = flow_analysis.get('smart_money_signal', 'neutral')
        flow_direction = flow_analysis.get('flow_direction', 'neutral')

        if form13f_count > 0:
            if smart_signal == 'bullish':
                insights.append(f"🐂 Bullish Smart Money: {form13f_count} Form 13F filings - สถาบันเพิ่มการลงทุน")
            elif smart_signal == 'bearish':
                insights.append(f"🐻 Bearish Smart Money: {form13f_count} Form 13F filings - สถาบันลดการลงทุน")
            elif flow_direction == 'increasing':
                insights.append(f"📊 Increasing Institutional Interest: {form13f_count} Form 13F filings")
            else:
                insights.append(f"🏢 Institutional Activity: {form13f_count} Form 13F filings - มีความสนใจจากสถาบัน")
        else:
            insights.append("🏦 Limited Institutional Coverage - ข้อมูลสถาบันจำกัด")

        # Risk and opportunity insights
        risk_alerts = insider_data.get('risk_alerts', [])
        institutional_alerts = institutional_data.get('institutional_alerts', [])

        if risk_alerts:
            high_risk_alerts = [alert for alert in risk_alerts if alert.get('severity') == 'warning']
            if high_risk_alerts:
                insights.append(f"⚠️ Risk Alert: {high_risk_alerts[0].get('message', 'ตรวจพบสัญญาณเตือน')}")

        if institutional_alerts:
            positive_alerts = [alert for alert in institutional_alerts if alert.get('severity') == 'positive']
            if positive_alerts:
                insights.append(f"✅ Opportunity: {positive_alerts[0].get('message', 'พบโอกาสเชิงบวก')}")

        # Activity spike detection
        activity_spike = trend_analysis.get('activity_spike', False)
        if activity_spike:
            insights.append("🚨 Activity Spike Detected - ตรวจพบการเพิ่มขึ้นของกิจกรรมอย่างรวดเร็ว")

        # Data quality insight
        insights.append("🔗 Real-time SEC EDGAR API Data - ข้อมูลสดจาก SEC")

        return insights[:5]  # Return top 5 insights

    def _get_fallback_data(self) -> Dict[str, Any]:
        """Fallback data when ticker not found in SEC database"""
        return {
            'symbol': self.symbol,
            'cik': None,
            'insider_trading': {
                'recent_transactions': [],
                'insider_sentiment': 'unknown',
                'total_transactions': 0,
                'net_insider_activity': 0,
                'insider_confidence_score': 5,
                'has_real_data': False
            },
            'institutional_ownership': {
                'total_shares_held': 0,
                'ownership_percentage': 0,
                'top_institutions': [],
                'recent_changes': [],
                'institutional_confidence': 5,
                'has_real_data': False
            },
            'insider_score': 5,
            'institutional_score': 5,
            'combined_score': 5,
            'key_insights': [f'ไม่พบข้อมูล {self.symbol} ใน SEC EDGAR database'],
            'data_quality': 'ticker_not_found',
            'timestamp': datetime.now().isoformat(),
            'has_real_data': False
        }