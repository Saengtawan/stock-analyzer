#!/usr/bin/env python3
"""
AI Market Analyst
ใช้ DeepSeek AI สร้างการวิเคราะห์ตลาดและข่าวการเงินภาษาไทย
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from loguru import logger
from deepseek_service import deepseek_service
from news_service import news_service


class AIMarketAnalyst:
    """AI-powered market analysis and news generation"""

    def __init__(self):
        """Initialize AI Market Analyst"""
        self.deepseek_service = deepseek_service
        self.news_service = news_service

    def _call_deepseek_api(self, prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """
        Call DeepSeek API using centralized service

        Args:
            prompt: The prompt to send to AI
            max_tokens: Maximum tokens for response

        Returns:
            AI response text or None if failed
        """
        return self.deepseek_service.call_api(prompt, max_tokens, temperature=0.7)

    def generate_market_analysis(self) -> Dict[str, Any]:
        """
        สร้างการวิเคราะห์ตลาดและเหตุการณ์สำคัญที่จะเกิดขึ้นใน 1-3 เดือนข้างหน้า

        Returns:
            Dict containing market analysis with events and impacts
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        next_quarter = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

        # Fetch latest news from multiple financial sources using News Service
        logger.info("Fetching latest financial news...")
        recent_news = self.news_service.fetch_general_financial_news(max_articles=20)

        # Format news for context
        news_context = ""
        if recent_news:
            news_context = "CURRENT MARKET NEWS CONTEXT:\n"
            for i, article in enumerate(recent_news, 1):
                news_context += f"{i}. {article['title']}\n   Published: {article['published']}\n   Summary: {article['summary'][:200]}...\n\n"
        else:
            news_context = "CURRENT MARKET NEWS CONTEXT: No recent news available\n\n"

        prompt = ("You are an expert US stock and gold market analyst AI. Today's date: " + current_date + "\n\n" +
                  news_context +
                  "TASK: Based on the current news context above and market conditions, analyze the TOP 7 most important upcoming events (until " + next_quarter + ") that will significantly impact US stock market and gold prices.\n\n" +
                  "ANALYSIS GUIDELINES:\n" +
                  "- Use the current news context to understand market sentiment and ongoing developments\n" +
                  "- Focus on forward-looking events that build upon current market themes\n" +
                  "- Include Fed meetings, earnings seasons, economic data releases, geopolitical events\n" +
                  "- Rank by expected market impact (1 = highest impact)\n\n" +
                  "🔥 ENHANCED ANALYSIS REQUIREMENTS (NEW):\n" +
                  "For EACH event, you MUST analyze BOTH positive AND negative impacts:\n\n" +
                  "1. **ROOT CAUSE**: Explain WHY this event is happening\n" +
                  "   - Example: 'Trump raises tariffs BECAUSE China restricts rare earth exports'\n" +
                  "   - Example: 'Fed may cut rates BECAUSE inflation is cooling down'\n\n" +
                  "2. **EVENT DATE & TIMELINE**: Specify WHEN this will happen\n" +
                  "   - event_date: Exact date (YYYY-MM-DD) or approximate month\n" +
                  "   - impact_timeline: Break down impacts into time periods:\n" +
                  "     • Immediate (announcement day - 3 days): Market reaction\n" +
                  "     • Short-term (1-2 weeks): Which stocks start moving\n" +
                  "     • Medium-term (1-3 months): Full impact realized\n" +
                  "     • buy_timing: WHEN to buy winner stocks (specific dates/period)\n" +
                  "     • sell_timing: WHEN to sell loser stocks (before which date)\n" +
                  "   - Example: 'Trump announces tariff Oct 10 → Implement Nov 1'\n" +
                  "     - Immediate: S&P 500 drops 2.7% (happened)\n" +
                  "     - Short-term: AAPL continues falling (Oct 15-20)\n" +
                  "     - Medium-term: MP Materials rises (Oct 25 - Nov 30)\n" +
                  "     - buy_timing: Buy MP/CAT around Oct 20-25 before Nov 1\n" +
                  "     - sell_timing: Sell AAPL/TGT by Oct 15 before bigger drop\n\n" +
                  "3. **NEGATIVE IMPACT**: Which stocks/sectors will FALL and WHY?\n" +
                  "   - List specific stocks that will be hurt (with reasons)\n" +
                  "   - Example: AAPL, NVDA (rely on China manufacturing)\n\n" +
                  "4. **POSITIVE IMPACT**: Which stocks/sectors will RISE and WHY?\n" +
                  "   - List specific stocks that will benefit (with reasons)\n" +
                  "   - Example: MP (rare earth mining), LMT (defense), CAT (made in USA)\n\n" +
                  "5. **COMPREHENSIVE STOCK EXAMPLES**: Include BOTH winners AND losers\n" +
                  "   - Winners: Companies that benefit from the event\n" +
                  "   - Losers: Companies that are hurt by the event\n\n" +
                  "CRITICAL REQUIREMENTS:\n" +
                  "1. MUST respond with VALID JSON format ONLY\n" +
                  "2. NO additional text before or after JSON\n" +
                  "3. Use Thai language for content\n" +
                  "4. Include exactly 7 events ranked by market impact\n" +
                  "5. Base analysis on realistic upcoming events informed by current news\n" +
                  "6. MUST explain root cause, negative impact, AND positive impact for EVERY event\n\n" +
                  "JSON STRUCTURE (copy exactly, with NEW fields):\n" +
                  "{\n" +
                  '  "generated_at": "' + current_date + '",\n' +
                  '  "analysis_period": "1-3 เดือนข้างหน้า",\n' +
                  '  "market_summary": "สรุปภาพรวมตลาด",\n' +
                  '  "key_events": [\n' +
                  '    {\n' +
                  '      "rank": 1,\n' +
                  '      "event_name": "ชื่อเหตุการณ์",\n' +
                  '      "category": "เศรษฐกิจ",\n' +
                  '      "description": "รายละเอียดเหตุการณ์",\n' +
                  '      "root_cause": "สาเหตุที่แท้จริงว่าทำไมเหตุการณ์นี้เกิดขึ้น",\n' +
                  '      "current_status": "สถานะปัจจุบัน",\n' +
                  '      "event_date": "2025-11-01",\n' +
                  '      "event_date_description": "วันที่เหตุการณ์จะเกิดขึ้นจริง (ถ้ารู้แน่นอน) หรือประมาณเดือน",\n' +
                  '      "impact_timeline": {\n' +
                  '        "immediate": "ผลกระทบทันที (วันประกาศ-3 วันแรก): ตลาดตอบสนองอย่างไร",\n' +
                  '        "short_term": "ระยะสั้น (1-2 สัปดาห์): หุ้นไหนเริ่มเคลื่อนไหว",\n' +
                  '        "medium_term": "ระยะกลาง (1-3 เดือน): ผลกระทบเต็มรูปแบบ",\n' +
                  '        "buy_timing": "จังหวะเข้าซื้อหุ้นที่จะขึ้น: ช่วงเวลาที่เหมาะสม",\n' +
                  '        "sell_timing": "จังหวะขายหุ้นที่จะลง: ควรขายก่อนวันไหน"\n' +
                  '      },\n' +
                  '      "stock_impact": {"direction": "ลง", "reason": "เหตุผลที่ทำให้หุ้นส่วนใหญ่ลง"},\n' +
                  '      "gold_impact": {"direction": "ขึ้น", "reason": "เหตุผล"},\n' +
                  '      "negative_impact": {\n' +
                  '        "affected_sectors": ["เทคโนโลยี", "การผลิต"],\n' +
                  '        "loser_stocks": ["AAPL", "NVDA", "TGT"],\n' +
                  '        "reason": "เหตุผลที่หุ้นพวกนี้ได้รับผลกระทบเชิงลบ"\n' +
                  '      },\n' +
                  '      "positive_impact": {\n' +
                  '        "beneficiary_sectors": ["พลังงาน", "วัตถุดิบ", "ป้องกันประเทศ"],\n' +
                  '        "winner_stocks": ["MP", "LMT", "CAT"],\n' +
                  '        "reason": "เหตุผลที่หุ้นพวกนี้ได้รับประโยชน์"\n' +
                  '      },\n' +
                  '      "example_stocks": ["AAPL", "NVDA", "MP", "LMT"]\n' +
                  '    }\n' +
                  '  ]\n' +
                  '}')

        try:
            logger.info("Calling DeepSeek API for detailed market analysis...")
            ai_response = self._call_deepseek_api(prompt, max_tokens=6000)  # Increased for enhanced analysis

            if ai_response:
                logger.info("Successfully received detailed AI response")

                # Try to extract JSON from response with improved parsing
                import re

                def find_complete_json(text):
                    """Find complete JSON object by counting braces"""
                    start_idx = text.find('{')
                    if start_idx == -1:
                        return None

                    brace_count = 0
                    for i, char in enumerate(text[start_idx:], start_idx):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                return text[start_idx:i+1]
                    return None

                # With strict JSON format, AI should return pure JSON
                logger.info(f"AI response length: {len(ai_response)}")

                # Try direct JSON parsing first (no markdown wrapper expected)
                json_str = ai_response.strip()

                # Fallback: look for JSON in response if direct parsing fails
                if not json_str.startswith('{'):
                    json_str = find_complete_json(ai_response)
                    if json_str:
                        logger.info("Found JSON using brace counting method")

                if json_str:
                    try:
                        logger.info(f"Attempting to parse JSON of length: {len(json_str)}")
                        analysis_data = json.loads(json_str)

                        # Check if key_events exists and has data
                        if 'key_events' in analysis_data and len(analysis_data['key_events']) > 0:
                            analysis_data['success'] = True
                            analysis_data['raw_response'] = ai_response
                            logger.info(f"Successfully generated market analysis with {len(analysis_data['key_events'])} events")
                            return analysis_data
                        else:
                            logger.warning("Parsed JSON but key_events is empty or missing")
                            logger.info(f"JSON keys: {list(analysis_data.keys()) if isinstance(analysis_data, dict) else 'Not a dict'}")
                            # Try to save the events from raw response anyway
                            analysis_data['success'] = True
                            analysis_data['raw_response'] = ai_response
                            return analysis_data

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON from AI response: {e}")
                        logger.info(f"JSON string preview: {json_str[:500]}...")
                        # Return structured fallback
                        return self._get_fallback_analysis(ai_response)
                else:
                    logger.warning("No JSON found in AI response")
                    logger.info(f"Response preview: {ai_response[:500]}...")
                    return self._get_fallback_analysis(ai_response)
            else:
                logger.warning("No AI response received")
                return self._get_error_response("ไม่ได้รับการตอบสนองจาก AI")

        except Exception as e:
            logger.error(f"Error in generate_market_analysis: {e}")
            return self._get_error_response(f"เกิดข้อผิดพลาด: {str(e)}")

    def generate_additional_events(self) -> Dict[str, Any]:
        """
        สร้างเหตุการณ์เพิ่มเติมอีก 8 รายการ (รองจากอันดับที่ 8-15)

        Returns:
            Dict containing additional 8 events
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        next_quarter = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

        # Fetch latest news from multiple sources using News Service
        logger.info("Fetching latest financial news for additional events...")
        recent_news = self.news_service.fetch_general_financial_news(max_articles=15)

        # Format news for context
        news_context = ""
        if recent_news:
            news_context = "CURRENT MARKET NEWS CONTEXT:\n"
            for i, article in enumerate(recent_news, 1):
                news_context += f"{i}. {article['title']}\n   Published: {article['published']}\n   Summary: {article['summary'][:150]}...\n\n"
        else:
            news_context = "CURRENT MARKET NEWS CONTEXT: No recent news available\n\n"

        prompt = ("You are an expert US stock and gold market analyst AI. Today's date: " + current_date + "\n\n" +
                  news_context +
                  "TASK: Based on the current news context, analyze the NEXT 8 important upcoming events (rank 8-15) for the period until " + next_quarter + " that will impact US stock market and gold prices.\n\n" +
                  "ANALYSIS GUIDELINES:\n" +
                  "- Use the current news context to understand ongoing market themes\n" +
                  "- Focus on forward-looking events that complement the top 5 most critical events\n" +
                  "- Include Fed meetings, earnings seasons, economic data releases, geopolitical events\n" +
                  "- Rank by expected market impact (8-15, where 8 = moderately high impact)\n\n" +
                  "CRITICAL REQUIREMENTS:\n" +
                  "1. MUST respond with VALID JSON format ONLY\n" +
                  "2. NO additional text before or after JSON\n" +
                  "3. Use Thai language for content\n" +
                  "4. Include events ranked 8-15 by market impact\n\n" +
                  "JSON STRUCTURE (copy exactly):\n" +
                  "{\n" +
                  '  "generated_at": "' + current_date + '",\n' +
                  '  "analysis_period": "1-3 เดือนข้างหน้า",\n' +
                  '  "additional_events": [\n' +
                  '    {\n' +
                  '      "rank": 8,\n' +
                  '      "event_name": "ชื่อเหตุการณ์",\n' +
                  '      "category": "เศรษฐกิจ",\n' +
                  '      "description": "รายละเอียด",\n' +
                  '      "current_status": "สถานะปัจจุบัน",\n' +
                  '      "stock_impact": {"direction": "ขึ้น", "reason": "เหตุผล"},\n' +
                  '      "gold_impact": {"direction": "ขึ้น", "reason": "เหตุผล"},\n' +
                  '      "affected_sectors": ["เทคโนโลยี", "การเงิน"],\n' +
                  '      "example_stocks": ["AAPL", "MSFT"]\n' +
                  '    }\n' +
                  '  ]\n' +
                  '}')

        try:
            logger.info("Calling DeepSeek API for additional events...")
            ai_response = self._call_deepseek_api(prompt, max_tokens=4000)

            if ai_response:
                logger.info("Successfully received additional events response")

                # Try direct JSON parsing
                json_str = ai_response.strip()

                if not json_str.startswith('{'):
                    # Fallback: find JSON in response
                    start_idx = ai_response.find('{')
                    if start_idx != -1:
                        brace_count = 0
                        for i, char in enumerate(ai_response[start_idx:], start_idx):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_str = ai_response[start_idx:i+1]
                                    break

                if json_str:
                    try:
                        additional_data = json.loads(json_str)
                        if 'additional_events' in additional_data:
                            additional_data['success'] = True
                            return additional_data
                        else:
                            return {"additional_events": [], "success": False, "error": "No additional events found"}
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse additional events JSON: {e}")
                        return {"additional_events": [], "success": False, "error": "JSON parsing failed"}
                else:
                    return {"additional_events": [], "success": False, "error": "No valid JSON found"}
            else:
                return {"additional_events": [], "success": False, "error": "No AI response"}

        except Exception as e:
            logger.error(f"Error in generate_additional_events: {e}")
            return {"additional_events": [], "success": False, "error": str(e)}

    def _get_fallback_analysis(self, raw_response: str) -> Dict[str, Any]:
        """Create fallback analysis structure from raw AI response"""
        current_date = datetime.now().strftime("%Y-%m-%d")

        return {
            "generated_at": current_date,
            "analysis_period": "1-3 เดือนข้างหน้า",
            "market_summary": "การวิเคราะห์ตลาดจาก AI",
            "success": True,
            "raw_response": raw_response,
            "key_events": []
        }

    def _get_error_response(self, error_msg: str) -> Dict[str, Any]:
        """Create error response structure"""
        current_date = datetime.now().strftime("%Y-%m-%d")

        return {
            "generated_at": current_date,
            "analysis_period": "1-3 เดือนข้างหน้า",
            "market_summary": f"ไม่สามารถสร้างการวิเคราะห์ได้: {error_msg}",
            "success": False,
            "error": error_msg,
            "key_events": []
        }

    def generate_quick_market_insight(self) -> Dict[str, Any]:
        """
        สร้างการวิเคราะห์ตลาดแบบย่อสำหรับแสดงใน dashboard

        Returns:
            Dict containing quick market insight
        """
        current_date = datetime.now().strftime("%Y-%m-%d")

        prompt = ("Today's date: " + current_date + "\n\n" +
                  "Please provide a brief market analysis for the US stock market today. Include:\n\n" +
                  "1. **Market Overview Today** (2-3 sentences about current market conditions)\n" +
                  "2. **Key Factors to Watch** (3 important factors affecting the market)\n" +
                  "3. **Investor Advice** (2-3 sentences of practical guidance)\n\n" +
                  "**IMPORTANT: Respond in Thai language and format as JSON:**\n\n" +
                  "```json\n{\n" +
                  '    "date": "' + current_date + '",\n' +
                  '    "market_overview": "ภาพรวมตลาด",\n' +
                  '    "key_factors": ["ปัจจัย1", "ปัจจัย2", "ปัจจัย3"],\n' +
                  '    "investor_advice": "คำแนะนำ"\n' +
                  "}\n```")

        try:
            response = self._call_deepseek_api(prompt, max_tokens=1000)

            if response:
                import re
                json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    try:
                        insight_data = json.loads(json_str)
                        insight_data['success'] = True
                        return insight_data
                    except json.JSONDecodeError:
                        pass

                # Fallback to simple response
                return {
                    "date": current_date,
                    "market_overview": "ตลาดมีความผันผวนตามปัจจัยเศรษฐกิจ",
                    "key_factors": ["อัตราดอกเบี้ย Fed", "ข้อมูลเงินเฟ้อ", "ผลประกอบการบริษัท"],
                    "investor_advice": "ควรติดตามข่าวสารและการเปลี่ยนแปลงของตลาดอย่างใกล้ชิด",
                    "success": True
                }
            else:
                return {
                    "date": current_date,
                    "market_overview": "ไม่สามารถวิเคราะห์ตลาดได้ในขณะนี้",
                    "key_factors": [],
                    "investor_advice": "กรุณาลองใหม่อีกครั้ง",
                    "success": False
                }

        except Exception as e:
            logger.error(f"Error in generate_quick_market_insight: {e}")
            return {
                "date": current_date,
                "market_overview": f"เกิดข้อผิดพลาด: {str(e)}",
                "key_factors": [],
                "investor_advice": "กรุณาลองใหม่อีกครั้ง",
                "success": False
            }