#!/usr/bin/env python3
"""
All Factors Data Collector - เก็บข้อมูลทุกปัจจัยที่กระทบราคาหุ้น

ปัจจัยที่เก็บ:
1. Technical (ราคา, volume, indicators)
2. Fundamental (earnings, revenue, margins)
3. Macroeconomic (Fed, inflation, GDP)
4. Sector-specific (oil, semiconductors, housing)
5. Market sentiment (VIX, put/call, short interest)
6. News & Events (earnings calendar, analyst ratings)
7. Geopolitical (wars, trade tensions)
8. Social sentiment (Reddit, Twitter trends)

แหล่งข้อมูล:
- Yahoo Finance (ฟรี)
- FRED (Federal Reserve Economic Data) - ฟรี
- SEC EDGAR (Insider trading) - ฟรี
- Finviz (Screener data)
- NewsAPI / Google News
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import requests
except ImportError:
    requests = None


class AllFactorsCollector:
    """เก็บข้อมูลทุกปัจจัยที่กระทบราคาหุ้น"""

    # ===== FACTOR CATEGORIES =====

    # 1. Technical Indicators (คำนวณจากราคา)
    TECHNICAL_FACTORS = [
        'price', 'volume', 'ma20', 'ma50', 'ma200',
        'rsi', 'macd', 'accumulation', 'atr', 'bollinger_bands',
        'support', 'resistance', 'trend_strength'
    ]

    # 2. Fundamental Factors (งบการเงิน)
    FUNDAMENTAL_FACTORS = [
        'eps', 'revenue', 'profit_margin', 'pe_ratio', 'ps_ratio',
        'debt_to_equity', 'free_cash_flow', 'book_value',
        'dividend_yield', 'earnings_growth', 'revenue_growth'
    ]

    # 3. Macroeconomic Factors (เศรษฐกิจมหภาค)
    MACRO_FACTORS = [
        'fed_rate',           # อัตราดอกเบี้ย Fed
        'cpi',                # เงินเฟ้อ
        'gdp_growth',         # GDP
        'unemployment',       # อัตราว่างงาน
        'treasury_10y',       # พันธบัตร 10 ปี
        'treasury_2y',        # พันธบัตร 2 ปี
        'yield_curve',        # ส่วนต่าง yield
        'dollar_index',       # ค่าเงินดอลลาร์
    ]

    # 4. Market Sentiment (ความเชื่อมั่นตลาด)
    SENTIMENT_FACTORS = [
        'vix',                # Fear index
        'put_call_ratio',     # Options sentiment
        'short_interest',     # หุ้นที่ถูก short
        'margin_debt',        # เงินกู้ซื้อหุ้น
        'fund_flows',         # เงินไหลเข้าออก
        'retail_sentiment',   # ความเชื่อมั่นรายย่อย
        'institutional_buys', # สถาบันซื้อ
    ]

    # 5. Sector-Specific Factors (เฉพาะกลุ่ม)
    SECTOR_FACTORS = {
        'Energy': ['crude_oil', 'natural_gas', 'opec_production'],
        'Technology': ['semiconductor_index', 'cloud_spending', 'ai_adoption'],
        'Finance': ['bank_index', 'credit_spreads', 'loan_growth'],
        'Healthcare': ['biotech_index', 'drug_approvals', 'medicare_changes'],
        'Consumer': ['consumer_confidence', 'retail_sales', 'housing_starts'],
        'Industrial': ['pmi', 'capex', 'freight_rates'],
    }

    # 6. Events & Calendar
    EVENT_FACTORS = [
        'earnings_date',      # วันประกาศงบ
        'earnings_surprise',  # งบดี/ร้ายกว่าคาด
        'dividend_date',      # วันจ่ายปันผล
        'split_date',         # วัน split หุ้น
        'fed_meeting',        # วันประชุม Fed
        'economic_releases',  # ประกาศตัวเลขเศรษฐกิจ
    ]

    # 7. News & Sentiment Signals
    NEWS_FACTORS = [
        'analyst_rating',     # คำแนะนำนักวิเคราะห์
        'price_target',       # ราคาเป้าหมาย
        'insider_trading',    # Insider ซื้อ/ขาย
        'news_sentiment',     # ข่าวบวก/ลบ
        'social_mentions',    # พูดถึงใน social
    ]

    # 8. Geopolitical Factors
    GEOPOLITICAL_FACTORS = [
        'war_risk',           # ความเสี่ยงสงคราม
        'trade_tensions',     # ความตึงเครียดการค้า
        'sanctions',          # มาตรการคว่ำบาตร
        'supply_chain_risk',  # ความเสี่ยง supply chain
        'political_stability', # เสถียรภาพการเมือง
    ]

    # ===== FREE DATA SOURCES =====
    FREE_SOURCES = {
        'yahoo_finance': {
            'url': 'https://finance.yahoo.com',
            'data': ['price', 'fundamentals', 'earnings_calendar', 'analyst_ratings'],
            'limit': 'Unlimited',
        },
        'fred': {
            'url': 'https://fred.stlouisfed.org/docs/api/fred/',
            'data': ['fed_rate', 'cpi', 'gdp', 'unemployment', 'treasury_yields'],
            'limit': '500 requests/day',
            'api_key': 'required (free)',
        },
        'sec_edgar': {
            'url': 'https://www.sec.gov/cgi-bin/browse-edgar',
            'data': ['insider_trading', 'filings'],
            'limit': 'Unlimited',
        },
        'finviz': {
            'url': 'https://finviz.com',
            'data': ['screener', 'insider_trading', 'news'],
            'limit': 'Rate limited',
        },
        'reddit': {
            'url': 'https://www.reddit.com/dev/api/',
            'data': ['social_sentiment', 'mentions'],
            'limit': '60 requests/minute',
        },
        'newsapi': {
            'url': 'https://newsapi.org',
            'data': ['news_headlines', 'sentiment'],
            'limit': '100 requests/day (free)',
            'api_key': 'required (free tier)',
        },
    }

    def __init__(self, cache_dir: str = None):
        """Initialize collector"""
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'factors'
        )
        os.makedirs(self.cache_dir, exist_ok=True)
        self.collected_data = {}

    def collect_all_factors(self, symbol: str) -> Dict[str, Any]:
        """
        เก็บข้อมูลทุกปัจจัยสำหรับหุ้นตัวหนึ่ง

        Returns:
            Dict with all factor categories
        """
        factors = {
            'symbol': symbol,
            'collected_at': datetime.now().isoformat(),
            'technical': self._collect_technical(symbol),
            'fundamental': self._collect_fundamental(symbol),
            'macro': self._collect_macro(),
            'sentiment': self._collect_sentiment(),
            'sector': self._collect_sector_factors(symbol),
            'events': self._collect_events(symbol),
            'news': self._collect_news(symbol),
        }

        return factors

    def _collect_technical(self, symbol: str) -> Dict[str, float]:
        """เก็บ Technical indicators"""
        tech = {}

        if yf is None:
            return tech

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1y')

            if hist.empty:
                return tech

            # Price & Volume
            tech['price'] = float(hist['Close'].iloc[-1])
            tech['volume'] = float(hist['Volume'].iloc[-1])
            tech['avg_volume_20d'] = float(hist['Volume'].tail(20).mean())

            closes = hist['Close'].values

            # Moving Averages
            tech['ma20'] = float(np.mean(closes[-20:]))
            tech['ma50'] = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
            tech['ma200'] = float(np.mean(closes[-200:])) if len(closes) >= 200 else None

            # Price vs MAs
            if tech['ma20']:
                tech['price_vs_ma20'] = ((tech['price'] - tech['ma20']) / tech['ma20']) * 100
            if tech['ma50']:
                tech['price_vs_ma50'] = ((tech['price'] - tech['ma50']) / tech['ma50']) * 100

            # RSI
            tech['rsi'] = self._calculate_rsi(closes)

            # ATR %
            tech['atr_pct'] = self._calculate_atr_pct(hist)

            # Accumulation
            tech['accumulation'] = self._calculate_accumulation(
                hist['Close'].values,
                hist['Volume'].values
            )

            # 52-week high/low
            tech['52w_high'] = float(hist['High'].max())
            tech['52w_low'] = float(hist['Low'].min())
            tech['pct_from_52w_high'] = ((tech['price'] - tech['52w_high']) / tech['52w_high']) * 100

        except Exception as e:
            tech['error'] = str(e)

        return tech

    def _collect_fundamental(self, symbol: str) -> Dict[str, Any]:
        """เก็บ Fundamental data"""
        fund = {}

        if yf is None:
            return fund

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Valuation
            fund['pe_ratio'] = info.get('trailingPE')
            fund['forward_pe'] = info.get('forwardPE')
            fund['ps_ratio'] = info.get('priceToSalesTrailing12Months')
            fund['pb_ratio'] = info.get('priceToBook')
            fund['ev_to_ebitda'] = info.get('enterpriseToEbitda')

            # Profitability
            fund['profit_margin'] = info.get('profitMargins')
            fund['operating_margin'] = info.get('operatingMargins')
            fund['roe'] = info.get('returnOnEquity')
            fund['roa'] = info.get('returnOnAssets')

            # Growth
            fund['earnings_growth'] = info.get('earningsGrowth')
            fund['revenue_growth'] = info.get('revenueGrowth')

            # Dividend
            fund['dividend_yield'] = info.get('dividendYield')
            fund['payout_ratio'] = info.get('payoutRatio')

            # Balance Sheet
            fund['debt_to_equity'] = info.get('debtToEquity')
            fund['current_ratio'] = info.get('currentRatio')
            fund['quick_ratio'] = info.get('quickRatio')

            # Analyst Recommendations
            fund['recommendation'] = info.get('recommendationKey')
            fund['target_mean'] = info.get('targetMeanPrice')
            fund['target_high'] = info.get('targetHighPrice')
            fund['target_low'] = info.get('targetLowPrice')
            fund['analyst_count'] = info.get('numberOfAnalystOpinions')

        except Exception as e:
            fund['error'] = str(e)

        return fund

    def _collect_macro(self) -> Dict[str, Any]:
        """เก็บ Macroeconomic data"""
        macro = {}

        if yf is None:
            return macro

        try:
            # Treasury Yields
            tnx = yf.Ticker('^TNX')  # 10-Year Treasury
            tnx_hist = tnx.history(period='5d')
            if not tnx_hist.empty:
                macro['treasury_10y'] = float(tnx_hist['Close'].iloc[-1])

            # VIX
            vix = yf.Ticker('^VIX')
            vix_hist = vix.history(period='5d')
            if not vix_hist.empty:
                macro['vix'] = float(vix_hist['Close'].iloc[-1])
                macro['vix_5d_avg'] = float(vix_hist['Close'].mean())

            # Dollar Index
            dxy = yf.Ticker('DX-Y.NYB')
            dxy_hist = dxy.history(period='5d')
            if not dxy_hist.empty:
                macro['dollar_index'] = float(dxy_hist['Close'].iloc[-1])

            # SPY (market trend)
            spy = yf.Ticker('SPY')
            spy_hist = spy.history(period='60d')
            if not spy_hist.empty:
                spy_close = float(spy_hist['Close'].iloc[-1])
                spy_ma20 = float(spy_hist['Close'].tail(20).mean())
                spy_ma50 = float(spy_hist['Close'].tail(50).mean())
                macro['spy_price'] = spy_close
                macro['spy_vs_ma20'] = ((spy_close - spy_ma20) / spy_ma20) * 100
                macro['spy_vs_ma50'] = ((spy_close - spy_ma50) / spy_ma50) * 100
                macro['market_trend'] = 'UP' if spy_close > spy_ma20 else 'DOWN'

        except Exception as e:
            macro['error'] = str(e)

        return macro

    def _collect_sentiment(self) -> Dict[str, Any]:
        """เก็บ Market sentiment data"""
        sentiment = {}

        if yf is None:
            return sentiment

        try:
            # VIX level interpretation
            vix = yf.Ticker('^VIX')
            vix_hist = vix.history(period='5d')
            if not vix_hist.empty:
                vix_val = float(vix_hist['Close'].iloc[-1])
                sentiment['vix'] = vix_val
                if vix_val < 15:
                    sentiment['fear_level'] = 'LOW'
                elif vix_val < 20:
                    sentiment['fear_level'] = 'NORMAL'
                elif vix_val < 30:
                    sentiment['fear_level'] = 'HIGH'
                else:
                    sentiment['fear_level'] = 'EXTREME'

            # Put/Call Ratio (would need options data)
            # sentiment['put_call_ratio'] = None  # Need options API

        except Exception as e:
            sentiment['error'] = str(e)

        return sentiment

    def _collect_sector_factors(self, symbol: str) -> Dict[str, Any]:
        """เก็บ Sector-specific factors"""
        sector_data = {}

        if yf is None:
            return sector_data

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            sector = info.get('sector', 'Unknown')
            industry = info.get('industry', 'Unknown')

            sector_data['sector'] = sector
            sector_data['industry'] = industry

            # Sector ETFs performance
            sector_etfs = {
                'Technology': 'XLK',
                'Financial Services': 'XLF',
                'Healthcare': 'XLV',
                'Consumer Cyclical': 'XLY',
                'Consumer Defensive': 'XLP',
                'Industrials': 'XLI',
                'Energy': 'XLE',
                'Real Estate': 'XLRE',
                'Utilities': 'XLU',
                'Basic Materials': 'XLB',
                'Communication Services': 'XLC',
            }

            if sector in sector_etfs:
                etf = yf.Ticker(sector_etfs[sector])
                etf_hist = etf.history(period='30d')
                if not etf_hist.empty:
                    first_price = float(etf_hist['Close'].iloc[0])
                    last_price = float(etf_hist['Close'].iloc[-1])
                    sector_data['sector_30d_return'] = ((last_price - first_price) / first_price) * 100

            # Sector-specific commodities
            if sector == 'Energy':
                oil = yf.Ticker('CL=F')  # Crude Oil
                oil_hist = oil.history(period='5d')
                if not oil_hist.empty:
                    sector_data['crude_oil'] = float(oil_hist['Close'].iloc[-1])

            elif sector == 'Technology':
                smh = yf.Ticker('SMH')  # Semiconductor ETF
                smh_hist = smh.history(period='30d')
                if not smh_hist.empty:
                    first = float(smh_hist['Close'].iloc[0])
                    last = float(smh_hist['Close'].iloc[-1])
                    sector_data['semiconductor_30d'] = ((last - first) / first) * 100

        except Exception as e:
            sector_data['error'] = str(e)

        return sector_data

    def _collect_events(self, symbol: str) -> Dict[str, Any]:
        """เก็บ Upcoming events"""
        events = {}

        if yf is None:
            return events

        try:
            ticker = yf.Ticker(symbol)
            calendar = ticker.calendar

            if calendar is not None and not calendar.empty:
                # Earnings date
                if 'Earnings Date' in calendar.index:
                    earnings_date = calendar.loc['Earnings Date']
                    if hasattr(earnings_date, 'iloc'):
                        events['next_earnings'] = str(earnings_date.iloc[0])
                    else:
                        events['next_earnings'] = str(earnings_date)

                # Dividend date
                if 'Dividend Date' in calendar.index:
                    events['dividend_date'] = str(calendar.loc['Dividend Date'])

            # Days to earnings
            if events.get('next_earnings'):
                try:
                    earn_date = pd.to_datetime(events['next_earnings'])
                    days_to_earn = (earn_date - pd.Timestamp.now()).days
                    events['days_to_earnings'] = days_to_earn
                    events['earnings_soon'] = days_to_earn <= 7
                except:
                    pass

        except Exception as e:
            events['error'] = str(e)

        return events

    def _collect_news(self, symbol: str) -> Dict[str, Any]:
        """เก็บ News & Analyst data"""
        news_data = {}

        if yf is None:
            return news_data

        try:
            ticker = yf.Ticker(symbol)

            # Analyst Recommendations
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                recent = recs.tail(5)
                news_data['recent_ratings'] = recent.to_dict('records')

                # Count by type
                if 'To Grade' in recent.columns:
                    grades = recent['To Grade'].value_counts().to_dict()
                    news_data['rating_counts'] = grades

            # Insider Trading
            insider = ticker.insider_transactions
            if insider is not None and not insider.empty:
                recent_insider = insider.head(10)
                news_data['recent_insider'] = recent_insider.to_dict('records')

                # Net insider activity
                if 'Shares' in recent_insider.columns:
                    buys = recent_insider[recent_insider['Shares'] > 0]['Shares'].sum()
                    sells = abs(recent_insider[recent_insider['Shares'] < 0]['Shares'].sum())
                    news_data['insider_buy_shares'] = int(buys)
                    news_data['insider_sell_shares'] = int(sells)
                    news_data['insider_net'] = 'BUY' if buys > sells else 'SELL'

        except Exception as e:
            news_data['error'] = str(e)

        return news_data

    # ===== HELPER FUNCTIONS =====

    def _calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        if avg_loss == 0:
            return 100.0
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calculate_atr_pct(self, hist, period=14):
        if len(hist) < period:
            return 5.0
        closes = hist['Close'].values
        highs = hist['High'].values
        lows = hist['Low'].values
        tr = []
        for i in range(1, len(hist)):
            tr.append(max(
                float(highs[i]) - float(lows[i]),
                abs(float(highs[i]) - float(closes[i-1])),
                abs(float(lows[i]) - float(closes[i-1]))
            ))
        atr = np.mean(tr[-period:])
        price = float(closes[-1])
        return (atr / price) * 100 if price > 0 else 5.0

    def _calculate_accumulation(self, closes, volumes, period=20):
        if len(closes) < period:
            return 1.0
        up_vol, down_vol = 0.0, 0.0
        for i in range(-period+1, 0):
            if closes[i] > closes[i-1]:
                up_vol += volumes[i]
            elif closes[i] < closes[i-1]:
                down_vol += volumes[i]
        return up_vol / down_vol if down_vol > 0 else 3.0

    def save_factors(self, symbol: str, factors: Dict) -> str:
        """Save collected factors to JSON file"""
        filename = f"{symbol}_factors_{datetime.now().strftime('%Y%m%d')}.json"
        filepath = os.path.join(self.cache_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(factors, f, indent=2, default=str)

        return filepath

    def print_all_factors_needed(self):
        """Print summary of all factors we should track"""
        print("=" * 80)
        print("ALL FACTORS THAT AFFECT STOCK PRICES")
        print("=" * 80)

        categories = {
            'Technical': self.TECHNICAL_FACTORS,
            'Fundamental': self.FUNDAMENTAL_FACTORS,
            'Macroeconomic': self.MACRO_FACTORS,
            'Market Sentiment': self.SENTIMENT_FACTORS,
            'Events & Calendar': self.EVENT_FACTORS,
            'News & Analyst': self.NEWS_FACTORS,
            'Geopolitical': self.GEOPOLITICAL_FACTORS,
        }

        for cat_name, factors in categories.items():
            print(f"\n{cat_name}:")
            for f in factors:
                print(f"  - {f}")

        print("\n" + "=" * 80)
        print("SECTOR-SPECIFIC FACTORS")
        print("=" * 80)

        for sector, factors in self.SECTOR_FACTORS.items():
            print(f"\n{sector}:")
            for f in factors:
                print(f"  - {f}")

        print("\n" + "=" * 80)
        print("FREE DATA SOURCES")
        print("=" * 80)

        for source, info in self.FREE_SOURCES.items():
            print(f"\n{source}:")
            print(f"  URL: {info['url']}")
            print(f"  Data: {', '.join(info['data'])}")
            print(f"  Limit: {info['limit']}")


def demo():
    """Demo the collector"""
    collector = AllFactorsCollector()

    # Print all factors we should track
    collector.print_all_factors_needed()

    # Collect data for a sample stock
    print("\n" + "=" * 80)
    print("DEMO: Collecting all factors for AAPL")
    print("=" * 80)

    factors = collector.collect_all_factors('AAPL')

    # Print summary
    print("\nTechnical Factors:")
    for k, v in factors['technical'].items():
        if v is not None:
            print(f"  {k}: {v}")

    print("\nFundamental Factors:")
    for k, v in factors['fundamental'].items():
        if v is not None:
            print(f"  {k}: {v}")

    print("\nMacro Factors:")
    for k, v in factors['macro'].items():
        if v is not None:
            print(f"  {k}: {v}")

    print("\nSector Factors:")
    for k, v in factors['sector'].items():
        if v is not None:
            print(f"  {k}: {v}")

    print("\nUpcoming Events:")
    for k, v in factors['events'].items():
        if v is not None:
            print(f"  {k}: {v}")

    # Save to file
    filepath = collector.save_factors('AAPL', factors)
    print(f"\nSaved to: {filepath}")


if __name__ == '__main__':
    demo()
