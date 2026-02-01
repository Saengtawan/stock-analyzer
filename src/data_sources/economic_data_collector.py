#!/usr/bin/env python3
"""
Economic Data Collector - ดึงข้อมูลเศรษฐกิจจาก FRED (ฟรี)

FRED (Federal Reserve Economic Data) ให้ข้อมูล:
- Fed Fund Rate (อัตราดอกเบี้ย)
- CPI (เงินเฟ้อ)
- GDP Growth
- Unemployment Rate
- Treasury Yields
- และอีกมากมาย

ข้อมูลเหล่านี้มีผลกระทบต่อตลาดหุ้นโดยตรง!
"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional
import warnings
warnings.filterwarnings('ignore')

try:
    import requests
except ImportError:
    requests = None


class EconomicDataCollector:
    """
    ดึงข้อมูลเศรษฐกิจจาก FRED API

    FRED API: https://fred.stlouisfed.org/docs/api/fred/
    สมัคร API Key ฟรี: https://fred.stlouisfed.org/docs/api/api_key.html
    """

    # ===== KEY ECONOMIC INDICATORS =====

    # ตัวเลขสำคัญที่มีผลต่อตลาดหุ้น
    KEY_INDICATORS = {
        # Interest Rates (อัตราดอกเบี้ย)
        'FEDFUNDS': {
            'name': 'Federal Funds Rate',
            'description': 'อัตราดอกเบี้ยนโยบายของ Fed',
            'impact': 'สูง = หุ้นลง (ต้นทุนกู้ยืมสูง)',
            'frequency': 'Monthly',
        },
        'DFF': {
            'name': 'Effective Federal Funds Rate',
            'description': 'อัตราดอกเบี้ยจริงในตลาด',
            'impact': 'ดูแนวโน้มนโยบายการเงิน',
            'frequency': 'Daily',
        },

        # Treasury Yields (ผลตอบแทนพันธบัตร)
        'DGS10': {
            'name': '10-Year Treasury Yield',
            'description': 'ผลตอบแทนพันธบัตร 10 ปี',
            'impact': 'สูง = หุ้น growth ลง',
            'frequency': 'Daily',
        },
        'DGS2': {
            'name': '2-Year Treasury Yield',
            'description': 'ผลตอบแทนพันธบัตร 2 ปี',
            'impact': 'ดูความคาดหวังดอกเบี้ย',
            'frequency': 'Daily',
        },
        'T10Y2Y': {
            'name': 'Yield Curve (10Y-2Y)',
            'description': 'ส่วนต่าง yield 10 ปี vs 2 ปี',
            'impact': 'ติดลบ = เสี่ยง recession',
            'frequency': 'Daily',
        },

        # Inflation (เงินเฟ้อ)
        'CPIAUCSL': {
            'name': 'Consumer Price Index',
            'description': 'ดัชนีราคาผู้บริโภค (CPI)',
            'impact': 'สูง = Fed ขึ้นดอกเบี้ย',
            'frequency': 'Monthly',
        },
        'CPILFESL': {
            'name': 'Core CPI (ex Food & Energy)',
            'description': 'CPI พื้นฐาน (ไม่รวมอาหาร/พลังงาน)',
            'impact': 'ตัวเลขที่ Fed ดู',
            'frequency': 'Monthly',
        },
        'PCEPI': {
            'name': 'PCE Price Index',
            'description': 'ดัชนีราคา PCE (Fed ชอบดู)',
            'impact': 'เป้าหมาย Fed = 2%',
            'frequency': 'Monthly',
        },

        # Employment (การจ้างงาน)
        'UNRATE': {
            'name': 'Unemployment Rate',
            'description': 'อัตราว่างงาน',
            'impact': 'ต่ำ = เศรษฐกิจดี',
            'frequency': 'Monthly',
        },
        'PAYEMS': {
            'name': 'Nonfarm Payrolls',
            'description': 'จำนวนการจ้างงาน',
            'impact': 'เพิ่ม = เศรษฐกิจดี',
            'frequency': 'Monthly',
        },
        'ICSA': {
            'name': 'Initial Jobless Claims',
            'description': 'ผู้ขอรับสวัสดิการว่างงานใหม่',
            'impact': 'สูง = เศรษฐกิจแย่',
            'frequency': 'Weekly',
        },

        # GDP & Economic Activity
        'GDP': {
            'name': 'Gross Domestic Product',
            'description': 'ผลิตภัณฑ์มวลรวม',
            'impact': 'เพิ่ม = เศรษฐกิจโต',
            'frequency': 'Quarterly',
        },
        'GDPC1': {
            'name': 'Real GDP',
            'description': 'GDP ปรับเงินเฟ้อแล้ว',
            'impact': 'ตัวเลขจริงๆ ของการเติบโต',
            'frequency': 'Quarterly',
        },

        # Consumer & Business
        'UMCSENT': {
            'name': 'Consumer Sentiment',
            'description': 'ความเชื่อมั่นผู้บริโภค',
            'impact': 'สูง = จะใช้จ่ายมาก',
            'frequency': 'Monthly',
        },
        'RSAFS': {
            'name': 'Retail Sales',
            'description': 'ยอดค้าปลีก',
            'impact': 'สูง = Consumer spending ดี',
            'frequency': 'Monthly',
        },
        'ISM': {
            'name': 'ISM Manufacturing PMI',
            'description': 'ดัชนีผู้จัดการฝ่ายจัดซื้อ',
            'impact': '>50 = ภาคการผลิตขยายตัว',
            'frequency': 'Monthly',
        },

        # Housing
        'HOUST': {
            'name': 'Housing Starts',
            'description': 'บ้านเริ่มก่อสร้างใหม่',
            'impact': 'สูง = อสังหาฯ ดี',
            'frequency': 'Monthly',
        },
        'MORTGAGE30US': {
            'name': '30-Year Mortgage Rate',
            'description': 'อัตราดอกเบี้ยบ้าน 30 ปี',
            'impact': 'สูง = อสังหาฯ ชะลอ',
            'frequency': 'Weekly',
        },

        # Money Supply
        'M2SL': {
            'name': 'M2 Money Stock',
            'description': 'ปริมาณเงินในระบบ',
            'impact': 'เพิ่ม = เงินเฟ้อ, หุ้นขึ้น',
            'frequency': 'Monthly',
        },

        # Market Indicators
        'VIXCLS': {
            'name': 'VIX Index',
            'description': 'ดัชนีความกลัว',
            'impact': 'สูง = ตลาดกลัว',
            'frequency': 'Daily',
        },
        'DTWEXBGS': {
            'name': 'Dollar Index',
            'description': 'ค่าเงินดอลลาร์',
            'impact': 'แข็ง = หุ้นลง',
            'frequency': 'Daily',
        },
    }

    # Sector-specific indicators
    SECTOR_INDICATORS = {
        'Energy': {
            'DCOILWTICO': 'WTI Crude Oil Price',
            'DHHNGSP': 'Henry Hub Natural Gas Price',
        },
        'Real Estate': {
            'CSUSHPISA': 'Case-Shiller Home Price Index',
            'HOUST': 'Housing Starts',
        },
        'Consumer': {
            'UMCSENT': 'Consumer Sentiment',
            'RSAFS': 'Retail Sales',
        },
        'Financial': {
            'BAMLC0A0CM': 'Corporate Bond Spread',
            'TEDRATE': 'TED Spread',
        },
    }

    def __init__(self, api_key: str = None):
        """
        Initialize with FRED API key

        Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html
        """
        self.api_key = api_key or os.environ.get('FRED_API_KEY')
        self.base_url = "https://api.stlouisfed.org/fred"
        self.cache_dir = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'economic'
        )
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_series(self, series_id: str, start_date: str = None) -> pd.DataFrame:
        """
        Fetch a single data series from FRED

        Args:
            series_id: FRED series ID (e.g., 'FEDFUNDS')
            start_date: Start date (YYYY-MM-DD)

        Returns:
            DataFrame with date and value columns
        """
        if self.api_key is None:
            print("Warning: No FRED API key. Using fallback data.")
            return self._get_fallback_data(series_id)

        if requests is None:
            print("Warning: requests library not available")
            return pd.DataFrame()

        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

        url = f"{self.base_url}/series/observations"
        params = {
            'series_id': series_id,
            'api_key': self.api_key,
            'file_type': 'json',
            'observation_start': start_date,
        }

        try:
            response = requests.get(url, params=params)
            data = response.json()

            if 'observations' in data:
                df = pd.DataFrame(data['observations'])
                df['date'] = pd.to_datetime(df['date'])
                df['value'] = pd.to_numeric(df['value'], errors='coerce')
                return df[['date', 'value']].dropna()
            else:
                return pd.DataFrame()

        except Exception as e:
            print(f"Error fetching {series_id}: {e}")
            return pd.DataFrame()

    def _get_fallback_data(self, series_id: str) -> pd.DataFrame:
        """Get fallback data when no API key"""
        # Return empty DataFrame - user needs to set up API key
        return pd.DataFrame()

    def fetch_all_key_indicators(self) -> Dict[str, pd.DataFrame]:
        """Fetch all key economic indicators"""
        data = {}

        for series_id, info in self.KEY_INDICATORS.items():
            print(f"Fetching {info['name']}...")
            df = self.fetch_series(series_id)
            if not df.empty:
                data[series_id] = df

        return data

    def get_current_values(self) -> Dict[str, Dict]:
        """Get current value of all key indicators"""
        current = {}

        for series_id, info in self.KEY_INDICATORS.items():
            df = self.fetch_series(series_id)
            if not df.empty:
                latest = df.iloc[-1]
                current[series_id] = {
                    'name': info['name'],
                    'value': float(latest['value']),
                    'date': latest['date'].strftime('%Y-%m-%d'),
                    'impact': info['impact'],
                }

        return current

    def analyze_market_conditions(self) -> Dict[str, str]:
        """Analyze current market conditions based on economic data"""
        analysis = {
            'overall': 'NEUTRAL',
            'factors': [],
            'warnings': [],
        }

        current = self.get_current_values()

        # Check Fed Rate
        if 'DFF' in current:
            rate = current['DFF']['value']
            if rate > 5:
                analysis['warnings'].append(f"High Fed Rate ({rate:.2f}%) - Tight monetary policy")
                analysis['factors'].append('BEARISH: High interest rates')
            elif rate < 2:
                analysis['factors'].append('BULLISH: Low interest rates')

        # Check Yield Curve
        if 'T10Y2Y' in current:
            spread = current['T10Y2Y']['value']
            if spread < 0:
                analysis['warnings'].append(f"Inverted Yield Curve ({spread:.2f}%) - Recession signal")
                analysis['factors'].append('BEARISH: Inverted yield curve')

        # Check Unemployment
        if 'UNRATE' in current:
            unemp = current['UNRATE']['value']
            if unemp > 5:
                analysis['warnings'].append(f"High Unemployment ({unemp:.1f}%)")
                analysis['factors'].append('BEARISH: High unemployment')
            elif unemp < 4:
                analysis['factors'].append('BULLISH: Low unemployment')

        # Check VIX
        if 'VIXCLS' in current:
            vix = current['VIXCLS']['value']
            if vix > 25:
                analysis['warnings'].append(f"High VIX ({vix:.1f}) - Market fear")
                analysis['factors'].append('BEARISH: High volatility')
            elif vix < 15:
                analysis['factors'].append('BULLISH: Low volatility')

        # Determine overall
        bullish = sum(1 for f in analysis['factors'] if 'BULLISH' in f)
        bearish = sum(1 for f in analysis['factors'] if 'BEARISH' in f)

        if bullish > bearish + 1:
            analysis['overall'] = 'BULLISH'
        elif bearish > bullish + 1:
            analysis['overall'] = 'BEARISH'
        else:
            analysis['overall'] = 'NEUTRAL'

        return analysis

    def get_fed_calendar(self) -> list:
        """Get upcoming Fed meeting dates"""
        # 2024-2025 Fed meeting dates (approximate)
        fed_meetings = [
            '2025-01-29',
            '2025-03-19',
            '2025-05-07',
            '2025-06-18',
            '2025-07-30',
            '2025-09-17',
            '2025-11-05',
            '2025-12-17',
        ]

        today = datetime.now().date()
        upcoming = []

        for date_str in fed_meetings:
            meeting_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if meeting_date >= today:
                days_until = (meeting_date - today).days
                upcoming.append({
                    'date': date_str,
                    'days_until': days_until,
                    'warning': days_until <= 7
                })

        return upcoming

    def print_indicators_info(self):
        """Print information about all tracked indicators"""
        print("=" * 80)
        print("ECONOMIC INDICATORS TRACKED (FRED)")
        print("=" * 80)

        categories = {
            'Interest Rates': ['FEDFUNDS', 'DFF'],
            'Treasury Yields': ['DGS10', 'DGS2', 'T10Y2Y'],
            'Inflation': ['CPIAUCSL', 'CPILFESL', 'PCEPI'],
            'Employment': ['UNRATE', 'PAYEMS', 'ICSA'],
            'GDP & Activity': ['GDP', 'GDPC1', 'ISM'],
            'Consumer': ['UMCSENT', 'RSAFS'],
            'Housing': ['HOUST', 'MORTGAGE30US'],
            'Market': ['VIXCLS', 'DTWEXBGS', 'M2SL'],
        }

        for cat_name, series_list in categories.items():
            print(f"\n{cat_name}:")
            for series_id in series_list:
                if series_id in self.KEY_INDICATORS:
                    info = self.KEY_INDICATORS[series_id]
                    print(f"  {series_id}: {info['name']}")
                    print(f"    Impact: {info['impact']}")

        print("\n" + "=" * 80)
        print("HOW TO GET FREE API KEY:")
        print("=" * 80)
        print("""
1. Go to: https://fred.stlouisfed.org/docs/api/api_key.html
2. Click "Request API Key"
3. Create a free account
4. Your API key will be emailed to you

Set the API key:
  export FRED_API_KEY=your_api_key_here

Or pass it directly:
  collector = EconomicDataCollector(api_key='your_key')
""")

    def save_to_cache(self, data: Dict) -> str:
        """Save economic data to cache"""
        filename = f"economic_data_{datetime.now().strftime('%Y%m%d')}.json"
        filepath = os.path.join(self.cache_dir, filename)

        # Convert DataFrames to dict for JSON
        save_data = {}
        for k, v in data.items():
            if isinstance(v, pd.DataFrame):
                save_data[k] = v.to_dict('records')
            else:
                save_data[k] = v

        with open(filepath, 'w') as f:
            json.dump(save_data, f, indent=2, default=str)

        return filepath


def demo():
    """Demo the collector"""
    collector = EconomicDataCollector()

    # Print indicator info
    collector.print_indicators_info()

    # Show Fed calendar
    print("\n" + "=" * 80)
    print("UPCOMING FED MEETINGS")
    print("=" * 80)

    for meeting in collector.get_fed_calendar():
        warning = " (SOON!)" if meeting['warning'] else ""
        print(f"  {meeting['date']} - in {meeting['days_until']} days{warning}")


if __name__ == '__main__':
    demo()
