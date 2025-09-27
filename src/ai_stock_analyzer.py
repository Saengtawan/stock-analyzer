#!/usr/bin/env python3
"""
AI Stock Analyzer
ใช้ Claude AI วิเคราะห์หุ้นแบบ real-time พร้อม insights และ recommendations
"""

import json
from typing import Dict, Any, Optional, List
from loguru import logger
from datetime import datetime
from deepseek_service import deepseek_service


class AIStockAnalyzer:
    """AI-powered stock analyzer using DeepSeek API"""

    def __init__(self):
        """Initialize AI Stock Analyzer"""
        self.deepseek_service = deepseek_service

    def analyze_stock_with_ai(self,
                             symbol: str,
                             fundamental_data: Dict[str, Any],
                             technical_data: Dict[str, Any],
                             current_price: float,
                             time_horizon: str = 'medium') -> Dict[str, Any]:
        """
        Analyze stock using AI with comprehensive data

        Args:
            symbol: Stock symbol
            fundamental_data: Fundamental analysis results
            technical_data: Technical analysis results
            current_price: Current stock price
            time_horizon: Investment time horizon

        Returns:
            AI analysis results with insights and recommendations
        """
        try:
            # Prepare data summary for AI
            data_summary = self._prepare_data_summary(
                symbol, fundamental_data, technical_data, current_price, time_horizon
            )

            # Create comprehensive AI prompt
            prompt = self._create_analysis_prompt(data_summary)

            # Call DeepSeek API
            logger.info(f"🤖 Calling DeepSeek AI for {symbol} analysis...")
            ai_response = self._call_deepseek_api(prompt)

            if ai_response:
                # Parse AI response
                ai_analysis = self._parse_ai_analysis(ai_response)

                if ai_analysis:
                    logger.info(f"✅ DeepSeek AI analysis completed for {symbol}")

                    # Get analyst consensus separately
                    try:
                        analyst_consensus = self._get_analyst_consensus(symbol, current_price)
                        if analyst_consensus:
                            ai_analysis['analyst_consensus'] = analyst_consensus
                            logger.info(f"✅ Analyst consensus added for {symbol}")
                    except Exception as e:
                        logger.warning(f"Failed to get analyst consensus for {symbol}: {e}")

                    # Extract confidence from summary or confidence_breakdown
                    summary = ai_analysis.get('summary', {})
                    confidence_breakdown = ai_analysis.get('confidence_breakdown', {})

                    # Priority: summary.confidence > confidence_breakdown.overall_confidence > fallback
                    ai_confidence = (
                        summary.get('confidence') or
                        confidence_breakdown.get('overall_confidence') or
                        ai_analysis.get('confidence', 0.5)
                    )

                    return {
                        'ai_analysis_available': True,
                        'analysis_summary': summary,
                        'current_situation': ai_analysis.get('current_situation', {}),
                        'market_context': ai_analysis.get('market_context', {}),
                        'risk_assessment': ai_analysis.get('risk_assessment', {}),
                        'price_targets': ai_analysis.get('price_targets', {}),
                        'catalyst_risk_map': ai_analysis.get('catalyst_risk_map', {}),
                        'valuation_benchmark': ai_analysis.get('valuation_benchmark', {}),
                        'sensitivity_analysis': ai_analysis.get('sensitivity_analysis', {}),
                        'positioning_strategy': ai_analysis.get('positioning_strategy', {}),
                        'shareholder_returns': ai_analysis.get('shareholder_returns', {}),
                        'analyst_consensus': ai_analysis.get('analyst_consensus', {}),
                        'investment_strategy': ai_analysis.get('investment_strategy', {}),
                        'key_insights': ai_analysis.get('key_insights', []),
                        'ai_confidence': ai_confidence,
                        'ai_timestamp': datetime.now().isoformat()
                    }

            logger.warning(f"DeepSeek AI analysis failed for {symbol}, using fallback")
            return self._get_fallback_analysis()

        except Exception as e:
            logger.error(f"AI analysis error for {symbol}: {e}")
            return self._get_fallback_analysis()

    def _prepare_data_summary(self, symbol: str, fundamental_data: Dict[str, Any],
                            technical_data: Dict[str, Any], current_price: float,
                            time_horizon: str) -> Dict[str, Any]:
        """Prepare concise data summary for AI analysis"""

        # Extract key fundamental metrics
        fund_ratios = fundamental_data.get('financial_ratios', {})
        fund_score = fundamental_data.get('overall_score', 0)

        # Extract key technical metrics
        tech_indicators = technical_data.get('indicators', {})
        tech_score = technical_data.get('technical_score', {}).get('total_score', 0)
        support_resistance = tech_indicators.get('support_resistance', {})

        return {
            'symbol': symbol,
            'current_price': current_price,
            'time_horizon': time_horizon,
            'fundamental': {
                'overall_score': fund_score,
                'pe_ratio': fund_ratios.get('pe_ratio'),
                'pb_ratio': fund_ratios.get('pb_ratio'),
                'roe': fund_ratios.get('roe'),
                'debt_to_equity': fund_ratios.get('debt_to_equity'),
                'revenue_growth': fund_ratios.get('revenue_growth'),
                'profit_margin': fund_ratios.get('profit_margin')
            },
            'technical': {
                'overall_score': tech_score,
                'rsi': tech_indicators.get('rsi'),
                'macd_line': tech_indicators.get('macd_line'),
                'macd_signal': tech_indicators.get('macd_signal'),
                'support_1': support_resistance.get('support_1'),
                'resistance_1': support_resistance.get('resistance_1'),
                'trend_direction': tech_indicators.get('trend_direction', 'neutral')
            }
        }

    def _create_analysis_prompt(self, data_summary: Dict[str, Any]) -> str:
        """Create comprehensive AI analysis prompt with enhanced logical reasoning"""

        symbol = data_summary['symbol']
        price = data_summary['current_price']
        horizon = data_summary['time_horizon']

        fund = data_summary['fundamental']
        tech = data_summary['technical']

        # Calculate data quality for confidence assessment
        data_completeness = sum(1 for v in fund.values() if v is not None and v != 'N/A') / len(fund)
        tech_completeness = sum(1 for v in tech.values() if v is not None and v != 'N/A') / len(tech)
        overall_data_quality = (data_completeness + tech_completeness) / 2

        prompt = f"""You are a Senior Equity Research Analyst with CFA designation and 20+ years of institutional investment experience. Conduct a comprehensive analysis of {symbol} stock with strict logical reasoning and structured methodology.

INVESTMENT CONTEXT:
- Symbol: {symbol}
- Current Price: ${price:.2f}
- Investment Horizon: {horizon}
- Data Quality Score: {overall_data_quality:.2f} (affects confidence)

FUNDAMENTAL METRICS ANALYSIS:
- Overall Score: {fund['overall_score']:.1f}/10
- P/E Ratio: {fund.get('pe_ratio', 'N/A')}
- P/B Ratio: {fund.get('pb_ratio', 'N/A')}
- ROE: {fund.get('roe', 'N/A')}
- Debt/Equity: {fund.get('debt_to_equity', 'N/A')}
- Revenue Growth: {fund.get('revenue_growth', 'N/A')}
- Profit Margin: {fund.get('profit_margin', 'N/A')}

TECHNICAL INDICATORS ANALYSIS:
- Overall Score: {tech['overall_score']:.1f}/10
- RSI: {tech.get('rsi', 'N/A')}
- MACD Line: {tech.get('macd_line', 'N/A')}
- MACD Signal: {tech.get('macd_signal', 'N/A')}
- Support Level: ${tech.get('support_1', 'N/A')}
- Resistance Level: ${tech.get('resistance_1', 'N/A')}
- Trend Direction: {tech.get('trend_direction', 'neutral')}

MANDATORY ANALYSIS FRAMEWORK:

1. LOGICAL REASONING SEPARATION:
   - Clearly separate fundamental-based reasoning from technical-based reasoning
   - Each reason must cite specific metrics and explain the logical connection
   - No generic statements - every point must be data-driven

2. MARKET CONTEXT ASSESSMENT:
   - Evaluate {symbol}'s sector positioning and relative performance
   - Assess correlation with broader market trends
   - Identify sector-specific catalysts or headwinds
   - Consider macroeconomic factors affecting this industry

3. CONFIDENCE METHODOLOGY:
   - Base confidence on data completeness ({overall_data_quality:.2f})
   - Adjust for metric reliability and consistency
   - Lower confidence for missing critical data points
   - Higher confidence for consistent fundamental-technical alignment

4. PRICE TARGETS METHODOLOGY:
   - High Target: Must have risk/reward ratio > 1.5:1 vs downside scenario
   - Average Target: Most probable scenario based on fundamental+technical convergence
   - Low Target: Conservative scenario considering downside risks and support levels
   - Stop Loss: Based on key technical levels (moving averages, psychological levels, volume support)
   - Each target must reference specific technical levels (support/resistance) and fundamental catalysts
   - Consider current distance from support/resistance when setting probability levels

5. HORIZON-SPECIFIC STRATEGY:
   - For {horizon} horizon: differentiate short-term (1-3 months) vs long-term (6+ months) within this timeframe
   - Provide tactical entry/exit points for short-term component
   - Provide strategic positioning for long-term component

6. STRICT JSON OUTPUT REQUIREMENTS:
   - Response MUST contain ONLY valid JSON - NO other text
   - JSON MUST be parseable with json.loads() without any preprocessing
   - NO explanations, comments, or markdown formatting
   - NO text before or after the JSON object
   - Use EXACT field names and data types as specified
   - All numeric values must be proper floats/integers
   - All strings must be properly quoted

MANDATORY JSON OUTPUT FORMAT (COPY EXACTLY):
{{
    "summary": {{
        "overall_score": <float 0.0-1.0>,
        "recommendation": "<BUY|HOLD|SELL>",
        "confidence": <float 0.0-1.0 based on data quality and analysis consistency>,
        "fundamental_reasons": [
            "Specific fundamental reason with metric citation",
            "Another fundamental reason with logical explanation"
        ],
        "technical_reasons": [
            "Specific technical reason with indicator citation",
            "Another technical reason with pattern explanation"
        ]
    }},
    "current_situation": {{
        "price_trend": "<bullish|bearish|sideways>",
        "trend_strength": "<strong|moderate|weak>",
        "momentum_direction": "<up|down|neutral>",
        "key_drivers": [
            "Primary factor driving current price movement",
            "Secondary factor affecting price direction"
        ],
        "recent_catalysts": [
            "Recent news/events affecting price",
            "Market developments impacting sentiment"
        ],
        "technical_status": "<oversold|overbought|neutral>",
        "support_resistance_status": "<near_support|near_resistance|between_levels>",
        "volume_confirmation": "<confirmed|weak|diverging>"
    }},
    "market_context": {{
        "sector_trend": "<outperforming|inline|underperforming>",
        "sector_correlation": "<strong|moderate|weak>",
        "market_regime": "<bull|bear|sideways>",
        "relative_strength": "<strong|average|weak>",
        "sector_catalysts": ["catalyst1", "catalyst2"],
        "macro_sensitivity": "<high|medium|low>"
    }},
    "risk_assessment": {{
        "overall_risk": "<low|medium|high>",
        "volatility_forecast": "<low|medium|high>",
        "fundamental_risks": ["risk1", "risk2"],
        "technical_risks": ["risk1", "risk2"],
        "risk_mitigation": "specific mitigation strategies"
    }},
    "price_targets": {{
        "high_target": {{
            "price": <float maximum target price>,
            "percentage_change": <float percentage from current price>,
            "timeframe": "timeframe to reach target",
            "probability": "<high|medium|low>"
        }},
        "average_target": {{
            "price": <float average target price>,
            "percentage_change": <float percentage from current price>,
            "timeframe": "timeframe to reach target",
            "probability": "<high|medium|low>"
        }},
        "low_target": {{
            "price": <float minimum target price>,
            "percentage_change": <float percentage from current price>,
            "timeframe": "timeframe to reach target",
            "probability": "<high|medium|low>"
        }},
        "stop_loss": {{
            "price": <float stop loss price>,
            "percentage_change": <float negative percentage from current price>,
            "reason": "reason for stop loss level"
        }}
    }},
    "investment_strategy": {{
        "short_term_strategy": {{
            "timeframe": "1-3 months",
            "approach": "tactical approach",
            "entry_levels": ["level1", "level2"],
            "exit_levels": ["target1", "stop_loss"]
        }},
        "long_term_strategy": {{
            "timeframe": "6+ months",
            "approach": "strategic positioning",
            "accumulation_strategy": "accumulation approach",
            "hold_criteria": "criteria for maintaining position"
        }},
        "position_sizing": "specific sizing recommendation",
        "risk_management": "specific risk management rules"
    }},
    "catalyst_risk_map": {{
        "short_term_catalysts": [
            "Near-term earnings/revenue drivers",
            "Upcoming product launches or announcements"
        ],
        "medium_term_catalysts": [
            "Regulatory changes or approvals",
            "Market expansion opportunities"
        ],
        "key_risks": [
            "Interest rate sensitivity impact",
            "Competitive threats from major players",
            "Currency volatility exposure"
        ],
        "risk_mitigation": "strategies to manage identified risks"
    }},
    "valuation_benchmark": {{
        "current_metrics": {{
            "pe_vs_industry": <float percentage difference>,
            "pb_vs_industry": <float percentage difference>,
            "ev_ebitda_vs_market": <float percentage difference>
        }},
        "valuation_status": "<discount|premium|inline>",
        "discount_premium": <float percentage discount or premium>,
        "peer_comparison": "comparison with similar companies",
        "fair_value_estimate": <float estimated fair value>
    }},
    "sensitivity_analysis": {{
        "earnings_scenarios": {{
            "bear_case": {{
                "eps_change": <float percentage change e.g. -15.0 for -15%>,
                "price_impact": <float percentage change from current price e.g. -12.5 for -12.5%>,
                "probability": "<high|medium|low>"
            }},
            "base_case": {{
                "eps_change": <float percentage change e.g. 8.0 for +8%>,
                "price_impact": <float percentage change from current price e.g. 10.0 for +10%>,
                "probability": "<high|medium|low>"
            }},
            "bull_case": {{
                "eps_change": <float percentage change e.g. 25.0 for +25%>,
                "price_impact": <float percentage change from current price e.g. 22.5 for +22.5%>,
                "probability": "<high|medium|low>"
            }}
        }},
        "key_sensitivities": [
            "Revenue growth sensitivity to market conditions",
            "Margin sensitivity to cost inflation"
        ]
    }},
    "positioning_strategy": {{
        "entry_approach": "specific entry strategy with price levels",
        "holding_strategy": "recommended holding period and criteria",
        "exit_strategy": "conditions for profit-taking or stop-loss",
        "position_sizing_rationale": "reasoning for recommended position size"
    }},
    "shareholder_returns": {{
        "dividend_info": {{
            "dividend_yield": <float current yield percentage>,
            "payout_ratio": <float payout ratio>,
            "sustainability": "<sustainable|at_risk|unsustainable>",
            "growth_outlook": "dividend growth prospects"
        }},
        "buyback_program": {{
            "active_program": <boolean>,
            "buyback_yield": <float percentage of market cap>,
            "program_duration": "timeline and scope",
            "effectiveness": "impact on shareholder value"
        }},
        "total_return_potential": "combined dividend and capital appreciation outlook"
    }},
    "uncertainty_factors": [
        "Factor 1: specific uncertainty with impact assessment",
        "Factor 2: another uncertainty with probability estimate"
    ],
    "confidence_breakdown": {{
        "data_quality": {overall_data_quality:.2f},
        "fundamental_confidence": "<high|medium|low>",
        "technical_confidence": "<high|medium|low>",
        "market_context_confidence": "<high|medium|low>",
        "overall_confidence": <float 0.0-1.0>
    }}
}}

CRITICAL REQUIREMENTS - FAILURE TO COMPLY WILL RESULT IN REJECTION:
- Every recommendation must have logical, data-driven justification
- Separate fundamental and technical reasoning explicitly
- Confidence must reflect actual data quality and analysis certainty
- Market context must be specific to {symbol}'s sector and characteristics
- Price targets must have balanced risk/reward ratio (minimum 1.5:1 for high target)
- Stop loss must be based on concrete technical levels, not arbitrary percentages
- Each target must cite specific support/resistance levels from current technical data
- Probability assessments must reflect current distance from technical levels
- Investment strategy must address both short-term and long-term components
- Response MUST be PURE JSON ONLY - absolutely no additional text, explanations, or formatting
- JSON must validate successfully with standard JSON parsers
- Response must start with {{ and end with }} - nothing else"""

        return prompt

    def _call_deepseek_api(self, prompt: str) -> str:
        """Call DeepSeek API for analysis using centralized service"""
        # Add system message for this specific use case
        full_prompt = """You are a Senior Equity Research Analyst with CFA designation and 20+ years of institutional investment experience.

""" + prompt

        response = self.deepseek_service.call_api(full_prompt, max_tokens=3072, temperature=0.1)
        return response or ""

    def _parse_ai_analysis(self, ai_response: str) -> Optional[Dict[str, Any]]:
        """Parse enhanced AI response into structured data"""
        try:
            # Clean response - remove any text before/after JSON
            import re

            # Find JSON block (more robust)
            json_pattern = r'\{(?:[^{}]|{[^{}]*})*\}'
            json_matches = re.findall(json_pattern, ai_response, re.DOTALL)

            if json_matches:
                # Try the largest JSON block (likely the main response)
                largest_json = max(json_matches, key=len)
                analysis = json.loads(largest_json)

                # Validate enhanced structure
                required_fields = ['summary', 'market_context', 'risk_assessment', 'investment_strategy']
                if all(field in analysis for field in required_fields):
                    # Validate confidence breakdown
                    confidence_data = analysis.get('confidence_breakdown', {})
                    if 'overall_confidence' in confidence_data:
                        # Use the detailed confidence assessment
                        analysis['confidence'] = confidence_data['overall_confidence']

                    # Merge fundamental and technical reasons if needed
                    summary = analysis.get('summary', {})
                    fund_reasons = summary.get('fundamental_reasons', [])
                    tech_reasons = summary.get('technical_reasons', [])

                    # Create combined key_reasons for backward compatibility
                    summary['key_reasons'] = fund_reasons + tech_reasons

                    logger.info("✅ Successfully parsed enhanced AI response with full structure")
                    return analysis

            # Fallback to simpler JSON parsing
            simple_json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if simple_json_match:
                analysis = json.loads(simple_json_match.group())

                # Basic validation for simple structure
                if 'summary' in analysis:
                    logger.warning("Parsed AI response with basic structure, missing some enhanced fields")
                    return analysis

            # No fallback - strict JSON requirement
            logger.error("Could not parse valid JSON from AI response")
            logger.error(f"Response content: {ai_response[:200]}...")
            return None

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.error(f"Invalid JSON response: {ai_response[:200]}...")
            return None
        except Exception as e:
            logger.error(f"Failed to parse AI analysis: {e}")
            return None


    def _get_fallback_analysis(self) -> Dict[str, Any]:
        """Fallback analysis when AI is unavailable - returns minimal unavailable status"""
        return {
            'ai_analysis_available': False,
            'analysis_skipped': True,
            'reason': 'AI analysis temporarily unavailable',
            'ai_timestamp': datetime.now().isoformat()
        }

    def _get_analyst_consensus(self, symbol: str, current_price: float) -> dict:
        """
        Get analyst consensus separately with focused prompt

        Args:
            symbol: Stock symbol
            current_price: Current stock price

        Returns:
            Dictionary with analyst consensus data
        """
        try:
            # Create enhanced analyst consensus prompt with strict accuracy requirements
            prompt = f"""You are a financial analyst assistant providing CURRENT Wall Street analyst consensus for {symbol} stock.

TIMEFRAME REQUIREMENT: Data must reflect Q4 2024 / Q1 2025 consensus only. Ignore outdated pre-2024 analyst data.

Current Price: ${current_price:.2f} (As of September 2024)

Please respond with ONLY a valid JSON object in this exact format:
{{
    "wall_street_consensus": {{
        "recommendation": "Buy",
        "target_price": 250.00,
        "analyst_count": 35,
        "data_quality": "estimated"
    }},
    "major_banks": {{
        "goldman_sachs_rating": "Buy",
        "morgan_stanley_rating": "Overweight",
        "average_target": 245.00,
        "data_quality": "estimated"
    }},
    "consensus_summary": {{
        "overall_sentiment": "Bullish",
        "bullish_percentage": 75.0,
        "last_updated": "Q4 2024"
    }}
}}

ENHANCED ACCURACY REQUIREMENTS:

TARGET PRICE VALIDATION:
- Target price must be within ±50% of current price (${current_price * 0.5:.2f} to ${current_price * 1.5:.2f}) unless recent major events justify otherwise
- If target price exceeds this range, provide clear justification (e.g., "Post-earnings revision", "Merger speculation")
- Use conservative estimates based on P/E and growth metrics if no reliable data exists
- Cross-validate targets against fundamental valuation models

ANALYST COUNT CONSTRAINTS:
- Large-cap stocks (>$50B market cap): 15-45 analysts (typical range: 25-35)
- Mid-cap stocks ($2B-$50B market cap): 8-25 analysts (typical range: 12-18)
- Small-cap stocks (<$2B market cap): 3-12 analysts (typical range: 5-8)
- ETFs and niche stocks: 2-10 analysts
- Popular tech/mega-cap stocks: 30-50+ analysts
- Consider {symbol} sector popularity and trading volume

DATA QUALITY INDICATORS & SOURCE-LEVEL GRANULARITY:
- "real": Verified recent analyst reports from last 90 days with specific dates
- "estimated": Reasonable projections based on historical patterns and current market conditions
- "not_available": Insufficient data, explicitly state this rather than guessing
- If estimated, specify confidence level (High/Medium/Low) and basis for estimate
- Include data freshness indicator: "Recent" (0-30 days), "Moderate" (30-90 days), "Stale" (90+ days)

VALIDATION RULES & CONSISTENCY CHECKS:
- Recommendation: Strong Buy, Buy, Hold, Sell, Strong Sell (must align with target price)
- Goldman ratings: Buy, Neutral, Sell (standardized format)
- Morgan Stanley ratings: Overweight, Equal-weight, Underweight (standardized format)
- Sentiment: Very Bullish, Bullish, Neutral, Bearish, Very Bearish
- Bullish percentage: 0-100 (must align with recommendation consensus and sentiment)
- Cross-validate: If recommendation is "Buy" but bullish_percentage < 60%, flag inconsistency

QUALITY CONTROL MECHANISMS:
- If you lack current analyst data, explicitly mark as "estimated" with confidence level
- Provide reasoning for estimates: "Based on sector averages", "Historical analyst patterns"
- Flag uncertainty: If target price range is wide, include range instead of single value
- Conservative bias: When uncertain, lean toward neutral recommendations and middle-range targets
- Avoid fabricating specific analyst names, dates, or price targets without verification

MARKET CONTEXT INTEGRATION:
- Consider current market volatility and sector-specific factors
- Adjust analyst count based on {symbol} trading volume and institutional interest
- Factor in recent earnings, guidance updates, or major corporate events
- Align recommendations with broader market sentiment and sector rotation trends"""

            # Call DeepSeek API with focused prompt
            response = self._call_deepseek_api(prompt)

            if response:
                # Log what AI returned for debugging
                logger.info(f"AI response for {symbol} analyst consensus: {response[:200]}...")

                # Parse JSON response
                try:
                    import json
                    response_clean = response.strip()

                    # Remove any markdown code blocks if present
                    if response_clean.startswith('```'):
                        lines = response_clean.split('\n')
                        # Find first line that looks like JSON
                        json_start = 0
                        for i, line in enumerate(lines):
                            if line.strip().startswith('{'):
                                json_start = i
                                break
                        # Find last }
                        json_end = len(lines)
                        for i in range(len(lines)-1, -1, -1):
                            if '}' in lines[i]:
                                json_end = i + 1
                                break
                        response_clean = '\n'.join(lines[json_start:json_end])

                    consensus_data = json.loads(response_clean)
                    logger.info(f"✅ Parsed analyst consensus for {symbol}")
                    return consensus_data
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse analyst consensus JSON for {symbol}: {e}")
                    logger.warning(f"Raw response: {response}")
                    return {}
            else:
                logger.warning(f"No response from AI for analyst consensus for {symbol}")
                return {}

        except Exception as e:
            logger.error(f"Error getting analyst consensus for {symbol}: {e}")
            return {}


def test_ai_analyzer():
    """Test AI Stock Analyzer"""
    print("=== Testing AI Stock Analyzer ===")

    analyzer = AIStockAnalyzer()

    # Mock data for testing
    test_fundamental = {
        'overall_score': 7.5,
        'financial_ratios': {
            'pe_ratio': 15.2,
            'pb_ratio': 2.1,
            'roe': 0.18,
            'debt_to_equity': 0.3,
            'revenue_growth': 0.12,
            'profit_margin': 0.15
        }
    }

    test_technical = {
        'technical_score': {'total_score': 6.8},
        'indicators': {
            'rsi': 45.2,
            'macd_line': 0.5,
            'macd_signal': 0.3,
            'support_resistance': {
                'support_1': 150.0,
                'resistance_1': 165.0
            },
            'trend_direction': 'bullish'
        }
    }

    result = analyzer.analyze_stock_with_ai(
        symbol='AAPL',
        fundamental_data=test_fundamental,
        technical_data=test_technical,
        current_price=155.50,
        time_horizon='medium'
    )

    print(f"AI Analysis Available: {result.get('ai_analysis_available', False)}")
    if result.get('analysis_summary'):
        summary = result['analysis_summary']
        print(f"Recommendation: {summary.get('recommendation', 'N/A')}")
        print(f"Confidence: {summary.get('confidence', 0)*100:.1f}%")
        print(f"Key Reasons: {summary.get('key_reasons', [])}")

    return result


if __name__ == "__main__":
    test_ai_analyzer()