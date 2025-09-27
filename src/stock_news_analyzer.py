"""
Stock News Analyzer - ดึงข่าวสำคัญและวิเคราะห์ผลกระทบต่อราคาหุ้น
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger
from deepseek_service import deepseek_service
from news_service import news_service

class StockNewsAnalyzer:
    """วิเคราะห์ข่าวสำคัญและผลกระทบต่อราคาหุ้น"""

    def __init__(self):
        self.deepseek_service = deepseek_service
        self.news_service = news_service

    def get_important_news_with_impact(self, symbol: str, timeframe: str = '1-3_months') -> Dict[str, Any]:
        """
        ดึงข่าวสำคัญและวิเคราะห์ผลกระทบต่อราคาหุ้น

        Args:
            symbol: รหัสหุ้น
            timeframe: ช่วงเวลา ('1-3_months', '1_month', '3_months')

        Returns:
            Dict containing news and impact analysis
        """
        try:
            logger.info(f"Analyzing important news for {symbol} with timeframe {timeframe}")

            # Generate news analysis using AI
            news_analysis = self._generate_news_analysis(symbol, timeframe)

            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'analysis_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'news': news_analysis.get('news', []),
                'overall_impact': news_analysis.get('overall_impact', {}),
                'success': True
            }

        except Exception as e:
            logger.error(f"Error analyzing news for {symbol}: {e}")
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'error': str(e),
                'news': [],
                'success': False
            }

    def _generate_news_analysis(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """Generate news analysis using AI with real news data"""

        # Determine timeframe description
        timeframe_desc = {
            '1_month': '1 เดือนข้างหน้า',
            '1-3_months': '1-3 เดือนข้างหน้า',
            '3_months': '3 เดือนข้างหน้า'
        }.get(timeframe, '1-3 เดือนข้างหน้า')

        current_date = datetime.now().strftime("%Y-%m-%d")

        # Fetch real news for the symbol using News Service
        logger.info(f"Fetching real news for {symbol}")
        recent_news = self.news_service.fetch_symbol_news(symbol, max_articles=8)

        # Prepare news context for AI
        news_context = ""
        if recent_news:
            news_context = "\n\nRECENT NEWS ARTICLES:\n"
            for i, article in enumerate(recent_news, 1):
                news_context += f"{i}. **{article['title']}** (Source: {article['source']}, Date: {article['published']})\n"
                news_context += f"   Summary: {article['summary']}\n\n"
        else:
            news_context = "\n\nNo recent specific news articles found for this symbol.\n"

        prompt = f"""Current Date: {current_date}

Analyze important news and events that will impact {symbol} stock price over the next {timeframe_desc} (timeframe in Thai).

{news_context}

CRITICAL: Respond ONLY in Thai language, but use your full English knowledge base for analysis.
IMPORTANT: Use the recent news articles above as primary data source for your analysis. Analyze these real articles and predict their impact on stock price.

Provide analysis in the following JSON format:

{{
    "news": [
        {{
            "title": "หัวข้อข่าวสำคัญ (in Thai)",
            "summary": "สรุปข่าวแบบย่อ (in Thai)",
            "date": "2025-01-15",
            "category": "earnings/product/regulation/market/partnership",
            "price_impact": "เชิงบวก/เชิงลบ/เป็นกลาง (in Thai)",
            "confidence": 85,
            "analysis": "การวิเคราะห์ผลกระทบอย่างละเอียด (in Thai)"
        }}
    ],
    "overall_impact": {{
        "direction": "เชิงบวก/เชิงลบ/เป็นกลาง (in Thai)",
        "summary": "สรุปผลกระทบรวม (in Thai)",
        "timeframe": "{timeframe_desc}"
    }}
}}

**IMPORTANT**: Use the current date ({current_date}) as the baseline for calculating the {timeframe_desc} timeframe.

Analyze based on these categories:
1. EARNINGS & FINANCIAL RESULTS - Quarterly earnings (Q1: March, Q2: June, Q3: September, Q4: December)
2. PRODUCT LAUNCHES & INNOVATION - New product releases, tech innovations
3. PARTNERSHIPS & ACQUISITIONS - Strategic alliances, M&A activities
4. REGULATORY CHANGES - Government policies, industry regulations
5. MARKET TRENDS - Industry trends, economic factors
6. MANAGEMENT CHANGES - Leadership changes, strategic shifts
7. ANALYST UPGRADES/DOWNGRADES - Wall Street analyst recommendations

Focus on:
- Events expected to occur between {current_date} and the next {timeframe_desc}
- High-impact news that significantly affects stock price
- Confidence assessment for news reliability (1-100 scale)
- Short-term and long-term implications
- Realistic future dates (must be after {current_date})
- Use comprehensive knowledge of US financial markets, earnings calendars, and industry cycles

If no major specific news, analyze general industry trends and macro factors that could impact the stock.

Remember: Respond entirely in Thai language using your full English knowledge base for superior analysis quality."""

        try:
            logger.info(f"Sending news analysis request for {symbol}")

            # Use centralized DeepSeek service
            news_data = self.deepseek_service.call_api_json(prompt, max_tokens=2000, temperature=0.3)

            if news_data:
                logger.info(f"Successfully parsed news analysis for {symbol}")
                return news_data
            else:
                raise ValueError("Failed to get valid JSON response from AI")

        except Exception as e:
            logger.error(f"Error generating news analysis for {symbol}: {e}")
            raise

def main():
    """Test the news analyzer"""
    analyzer = StockNewsAnalyzer()

    # Test with a popular stock
    symbol = "AAPL"
    print(f"Testing news analysis for {symbol}...")

    result = analyzer.get_important_news_with_impact(symbol, "1-3_months")

    print(f"\nResults for {symbol}:")
    print(f"Success: {result.get('success', False)}")
    print(f"Number of news items: {len(result.get('news', []))}")

    for i, news in enumerate(result.get('news', [])[:3], 1):
        print(f"\n{i}. {news.get('title', 'No title')}")
        print(f"   Impact: {news.get('price_impact', 'N/A')}")
        print(f"   Confidence: {news.get('confidence', 'N/A')}%")


if __name__ == "__main__":
    main()