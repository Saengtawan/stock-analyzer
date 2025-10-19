"""
AI Second Opinion - Cross-check system recommendations using DeepSeek Chat
"""
import json
from typing import Dict, Any, Optional
from loguru import logger
from deepseek_service import deepseek_service


class AISecondOpinion:
    """
    AI Second Opinion service that cross-checks all system recommendations
    using DeepSeek Chat for analysis
    """

    def __init__(self):
        self.deepseek_service = deepseek_service

    def analyze(self, analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze complete stock analysis results and provide AI second opinion

        Args:
            analysis_results: Complete analysis results from StockAnalyzer

        Returns:
            AI second opinion with verdict, reasons, and recommendations
        """
        try:
            logger.info(f"Generating AI Second Opinion for {analysis_results.get('symbol', 'Unknown')}")

            # Prepare comprehensive data for AI
            prompt_data = self._prepare_prompt_data(analysis_results)

            # Create prompt for DeepSeek Chat
            prompt = self._create_prompt(prompt_data)

            # Call DeepSeek Chat (use model='deepseek-chat')
            response = self.deepseek_service.call_api_json(
                prompt=prompt,
                max_tokens=3000,
                temperature=0.1,
                model='deepseek-chat'  # Use Chat for analysis
            )

            if response:
                logger.info(f"AI Second Opinion generated successfully for {prompt_data['symbol']}")
                logger.debug(f"AI Second Opinion raw response: {response}")
                return {
                    'success': True,
                    'ai_second_opinion': response,
                    'symbol': prompt_data['symbol']
                }
            else:
                logger.warning("No response from AI Second Opinion")
                return self._get_fallback_response(prompt_data['symbol'])

        except Exception as e:
            logger.error(f"Error generating AI Second Opinion: {e}")
            return self._get_error_response(str(e))

    def _prepare_prompt_data(self, analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare comprehensive data for AI analysis"""

        symbol = analysis_results.get('symbol', 'Unknown')
        current_price = analysis_results.get('current_price', 0)

        # Extract all recommendations
        unified = analysis_results.get('unified_recommendation', {})
        multi_tf = analysis_results.get('multi_timeframe_analysis', {})
        action_plan = analysis_results.get('action_plan', {})

        # Extract enhanced analysis
        enhanced = analysis_results.get('enhanced_analysis', {})
        technical = enhanced.get('technical_analysis', {})
        fundamental = enhanced.get('fundamental_analysis', {})
        market_state = technical.get('market_state_analysis', {})
        price_change = enhanced.get('price_change_analysis', {})

        # Extract component scores
        component_scores = unified.get('component_scores', {})

        # Extract indicators and signals
        indicators = technical.get('indicators', {})
        raw_signals = technical.get('raw_signals', {})
        sr_levels = technical.get('support_resistance', {})

        # Extract volume data from price_change_analysis
        volume_data = price_change.get('volume_analysis', {})

        return {
            'symbol': symbol,
            'current_price': current_price,

            # System Recommendations
            'unified_recommendation': {
                'recommendation': unified.get('recommendation', 'HOLD'),
                'score': unified.get('score', 5.0),
                'confidence': unified.get('confidence', 'MEDIUM'),
                'confidence_percentage': unified.get('confidence_percentage', 50),
                'reasoning': unified.get('reasoning', {})
            },

            'multi_timeframe': {
                'short': multi_tf.get('short', {}),
                'medium': multi_tf.get('medium', {}),
                'long': multi_tf.get('long', {}),
                'selected': multi_tf.get('selected', 'medium'),
                'alignment': multi_tf.get('alignment', {})
            },

            'market_state': {
                'current_state': market_state.get('current_state', 'UNKNOWN'),
                'strategy': market_state.get('strategy', {}),
                'confidence': market_state.get('confidence', {})
            },

            'action_plan': {
                'action_instruction': action_plan.get('action_instruction', ''),
                'position_size': action_plan.get('position_size_recommendation', ''),
                'entry': analysis_results.get('suggested_entry', 0),
                'stop_loss': analysis_results.get('suggested_stop_loss', 0),
                'take_profit': analysis_results.get('suggested_targets', [None])[0]
            },

            # Technical Data
            'technical': {
                'price_change': price_change.get('change_percent', 0),
                'gap': 'Gap Down' if price_change.get('direction') == 'DOWN' else 'Gap Up' if price_change.get('direction') == 'UP' else 'None',
                'gap_pct': abs(price_change.get('change_percent', 0)) if abs(price_change.get('change_percent', 0)) > 1 else 0,
                'momentum_5d': price_change.get('period_changes', {}).get('5_days', {}).get('change_percent', 0),
                'trend_strength': price_change.get('trend_strength', {}).get('strength', 50),
                'rsi': indicators.get('rsi', 50),
                'macd_histogram': indicators.get('macd_histogram', 0),
                'volume_vs_avg': (volume_data.get('volume_ratio', 1.0) - 1.0) * 100,  # Convert ratio to percentage vs average
                'support': sr_levels.get('support_1', 0),
                'resistance': sr_levels.get('resistance_1', 0)
            },

            # NEW: Historical Data (for trend analysis)
            'historical': {
                # Price changes over different periods
                'price_changes': {
                    '1_day': price_change.get('period_changes', {}).get('1_day', {}).get('change_percent', 0),
                    '5_days': price_change.get('period_changes', {}).get('5_days', {}).get('change_percent', 0),
                    '10_days': price_change.get('period_changes', {}).get('10_days', {}).get('change_percent', 0),
                    '20_days': price_change.get('period_changes', {}).get('20_days', {}).get('change_percent', 0),
                    '30_days': price_change.get('period_changes', {}).get('30_days', {}).get('change_percent', 0),
                    '60_days': price_change.get('period_changes', {}).get('60_days', {}).get('change_percent', 0)
                },
                # EMA/SMA positions for trend context
                'moving_averages': {
                    'ema_9': indicators.get('ema_9', 0),
                    'ema_21': indicators.get('ema_21', 0),
                    'ema_50': indicators.get('ema_50', 0),
                    'sma_50': indicators.get('sma_50', 0),
                    'sma_200': indicators.get('sma_200', 0),
                    'price_vs_ema9': ((current_price - indicators.get('ema_9', current_price)) / indicators.get('ema_9', current_price) * 100) if indicators.get('ema_9') else 0,
                    'price_vs_sma50': ((current_price - indicators.get('sma_50', current_price)) / indicators.get('sma_50', current_price) * 100) if indicators.get('sma_50') else 0,
                    'price_vs_sma200': ((current_price - indicators.get('sma_200', current_price)) / indicators.get('sma_200', current_price) * 100) if indicators.get('sma_200') else 0
                },
                # MACD trend
                'macd_trend': {
                    'macd_line': indicators.get('macd_line', 0),
                    'macd_signal': indicators.get('macd_signal', 0),
                    'macd_histogram': indicators.get('macd_histogram', 0),
                    'crossover': 'bullish' if indicators.get('macd_line', 0) > indicators.get('macd_signal', 0) else 'bearish'
                },
                # Volume trend
                'volume_trend': {
                    'current_vs_avg': (volume_data.get('volume_ratio', 1.0) - 1.0) * 100,
                    'trend': volume_data.get('trend', 'unknown'),
                    'volume_spike': volume_data.get('volume_ratio', 1.0) > 1.5
                },
                # Support/Resistance test history (if available)
                'sr_levels': {
                    'support_1': sr_levels.get('support_1', 0),
                    'support_2': sr_levels.get('support_2', 0),
                    'resistance_1': sr_levels.get('resistance_1', 0),
                    'resistance_2': sr_levels.get('resistance_2', 0),
                    'distance_to_support': ((current_price - sr_levels.get('support_1', current_price)) / current_price * 100) if sr_levels.get('support_1') else 0,
                    'distance_to_resistance': ((sr_levels.get('resistance_1', current_price) - current_price) / current_price * 100) if sr_levels.get('resistance_1') else 0
                }
            },

            # Fundamental Data
            'fundamental': {
                'score': fundamental.get('overall_score', 5.0),
                'pe_ratio': fundamental.get('financial_ratios', {}).get('pe_ratio'),
                'debt_to_equity': fundamental.get('financial_ratios', {}).get('debt_to_equity'),
                'roe': fundamental.get('financial_ratios', {}).get('roe'),
                'profit_margin': fundamental.get('financial_ratios', {}).get('profit_margin'),
                'insider_activity': fundamental.get('insider_analysis', {}).get('summary', '')
            },

            # Component Scores
            'component_scores': component_scores,

            # Risk/Reward (use unified recommendation R/R which is displayed on UI)
            'risk_reward': {
                'ratio': unified.get('risk_reward_analysis', {}).get('ratio', analysis_results.get('risk_reward_ratio', 1.0)),
                'entry': unified.get('risk_reward_analysis', {}).get('entry_price', analysis_results.get('suggested_entry', current_price)),
                'stop': unified.get('risk_reward_analysis', {}).get('stop_loss', analysis_results.get('suggested_stop_loss', 0)),
                'target': unified.get('risk_reward_analysis', {}).get('target_price', analysis_results.get('suggested_targets', [None])[0]),
                'risk_percentage': unified.get('risk_reward_analysis', {}).get('risk_percentage', 0),
                'reward_percentage': unified.get('risk_reward_analysis', {}).get('reward_percentage', 0)
            }
        }

    def _create_prompt(self, data: Dict[str, Any]) -> str:
        """Create comprehensive prompt for DeepSeek Reasoner"""

        symbol = data['symbol']
        current_price = data['current_price']

        unified = data['unified_recommendation']
        multi_tf = data['multi_timeframe']
        market_state = data['market_state']
        action_plan = data['action_plan']
        technical = data['technical']
        historical = data.get('historical', {})  # NEW: Historical data
        fundamental = data['fundamental']
        component_scores = data['component_scores']
        rr = data['risk_reward']

        prompt = f"""You are an expert AI trading analyst calculating **Performance Expectancy** for this trade setup.

**STOCK: {symbol}** | **PRICE: ${current_price}**

## SYSTEM RECOMMENDATION:
- **Action**: {unified['recommendation']}
- **Score**: {unified['score']}/10
- **Confidence**: {unified['confidence']} ({unified['confidence_percentage']}%)
- **Timeframe**: {multi_tf['selected'].upper()} (Short: {multi_tf.get('short', {}).get('score', 0):.1f}, Medium: {multi_tf.get('medium', {}).get('score', 0):.1f}, Long: {multi_tf.get('long', {}).get('score', 0):.1f})

## KEY DATA:

**Component Scores**:
- Technical: {component_scores.get('technical', 5.0):.1f}/10 | Fundamental: {component_scores.get('fundamental', 5.0):.1f}/10
- Momentum: {component_scores.get('momentum', 5.0):.1f}/10 | Risk/Reward: {component_scores.get('risk_reward', 5.0):.1f}/10
- Market State: {component_scores.get('market_state', 5.0):.1f}/10 | Insider: {component_scores.get('insider', 5.0):.1f}/10

**Risk/Reward**:
- R/R Ratio: {rr['ratio']:.2f}:1 (Risk: {rr.get('risk_percentage', 0):.1f}%, Reward: {rr.get('reward_percentage', 0):.1f}%)
- Entry: ${rr.get('entry', current_price):.2f} | Stop: ${rr.get('stop', 0):.2f} | Target: ${rr.get('target', 0):.2f}

**Technical Indicators**:
- RSI: {technical['rsi']:.1f} | MACD Histogram: {technical['macd_histogram']:.2f}
- Volume vs Avg: {technical['volume_vs_avg']:.0f}% | Price Change: {technical['price_change']:.1f}%
- Support: ${technical['support']:.2f} | Resistance: ${technical['resistance']:.2f}

**Fundamentals**:
- Score: {fundamental['score']:.1f}/10 | P/E: {fundamental.get('pe_ratio', 'N/A')} | ROE: {fundamental.get('roe', 'N/A')}
- Debt/Equity: {fundamental.get('debt_to_equity', 'N/A')} | Insider: {fundamental['insider_activity']}

**Trend** (30d/60d): {historical.get('price_changes', {}).get('30_days', 0):+.1f}% / {historical.get('price_changes', {}).get('60_days', 0):+.1f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## YOUR TASK:
Calculate the **Performance Expectancy** using this EXACT formula:

**Step 1: Calculate Base Win Probability from System Score**
- Score >= 7.0 → Base Win Rate = 65%
- Score 6.0-6.9 → Base Win Rate = 58%
- Score 5.0-5.9 → Base Win Rate = 52%
- Score 4.0-4.9 → Base Win Rate = 47%
- Score < 4.0 → Base Win Rate = 42%

**Step 2: Adjust by R/R Ratio**
- R/R >= 2.0 → Add +5%
- R/R >= 1.5 → Add +3%
- R/R < 1.0 → Subtract -5%

**Step 3: Adjust by Trend (30d/60d average)**
- Avg Trend > +10% → Add +5%
- Avg Trend > +5% → Add +3%
- Avg Trend < -5% → Subtract -3%
- Avg Trend < -10% → Subtract -5%

**Final Win Probability** = Base + R/R Adjustment + Trend Adjustment
**Loss Probability** = 100% - Win Probability

**Expectancy Calculation**:
- Use R/R ratio to estimate Avg Win/Loss
- Avg Win ≈ Reward %
- Avg Loss ≈ Risk %
- Expectancy = (Win% × Avg Win) - (Loss% × Avg Loss)

**CRITICAL**: Respond in **THAI LANGUAGE** using this JSON format:

{{
  "probability": {{
    "win_probability": XX,
    "lose_probability": YY,
    "expected_move": "อธิบายการเคลื่อนไหวที่คาดว่าจะเกิดตามข้อมูล 30/60 วัน"
  }},

  "expectancy": {{
    "total_trades": "ประมาณ X ครั้ง (ตามความถี่ของสัญญาณคล้ายกัน)",
    "win_rate": "XX%",
    "avg_win": "+X.X%",
    "avg_loss": "-X.X%",
    "expectancy_per_trade": "+X.X% per trade",
    "has_edge": true or false
  }}
}}

**IMPORTANT RULES**:
- Use THAI language for all text
- MUST follow the formula above - don't guess or add personal bias
- Win probability should MATCH system score quality (good score = good win rate)
- If score >= 6.5 AND R/R >= 1.5, Win% should be 55%+
- Don't be pessimistic - this is MATH, not opinion"""

        return prompt

    def _get_fallback_response(self, symbol: str) -> Dict[str, Any]:
        """Fallback response when AI call fails"""
        return {
            'success': False,
            'ai_second_opinion': {
                'verdict': 'NEUTRAL',
                'verdict_message': '⚠️ ไม่สามารถวิเคราะห์ได้ในขณะนี้',
                'ai_confidence': 0,
                'why_agree_or_disagree': [
                    {
                        'reason': 'ไม่สามารถเชื่อมต่อ AI ได้',
                        'detail': 'กรุณาลองใหม่อีกครั้ง',
                        'severity': 'LOW'
                    }
                ],
                'conflicts_detected': [],
                'probability': {
                    'win_probability': 50,
                    'lose_probability': 50,
                    'expected_move': 'ไม่สามารถประเมินได้'
                },
                'recommendation': {
                    'primary_action': '⚠️ รอการวิเคราะห์ที่สมบูรณ์',
                    'alternative_action': '✅ ใช้ดุลยพินิจของคุณเอง',
                    'wait_conditions': 'ลองใหม่ภายหลัง'
                }
            },
            'symbol': symbol
        }

    def _get_error_response(self, error_msg: str) -> Dict[str, Any]:
        """Error response"""
        return {
            'success': False,
            'error': error_msg,
            'ai_second_opinion': None
        }


# Global instance
ai_second_opinion_service = AISecondOpinion()


def main():
    """Test AI Second Opinion service"""
    print("Testing AI Second Opinion service...")

    # Mock analysis results
    mock_results = {
        'symbol': 'MARA',
        'current_price': 19.57,
        'unified_recommendation': {
            'recommendation': 'BUY',
            'score': 7.0,
            'confidence': 'LOW',
            'confidence_percentage': 45,
            'reasoning': {
                'strengths': ['Risk/Reward ดี', 'Momentum แข็งแรง'],
                'weaknesses': ['Fundamental อ่อน', 'Price Action ต่ำ']
            },
            'component_scores': {
                'technical': 7.1,
                'fundamental': 5.7,
                'momentum': 8.0,
                'market_state': 7.2,
                'risk_reward': 10.0,
                'insider': 6.4,
                'divergence': 5.0,
                'price_action': 4.5
            }
        },
        'multi_timeframe_analysis': {
            'short': {'recommendation': 'BUY', 'score': 7.2, 'confidence': 'LOW'},
            'medium': {'recommendation': 'BUY', 'score': 6.8, 'confidence': 'LOW'},
            'long': {'recommendation': 'BUY', 'score': 6.5, 'confidence': 'LOW'},
            'selected': 'medium',
            'alignment': {'all_aligned': True}
        },
        'enhanced_analysis': {
            'technical_analysis': {
                'indicators': {
                    'rsi': 52.7,
                    'macd_histogram': 0.05,
                    'support_resistance': {'support_1': 18.80, 'resistance_1': 19.70}
                },
                'price_data': {
                    'price_change_pct': -3.45,
                    'gap_type': 'Gap Down',
                    'gap_pct': -1.7,
                    'momentum_5d': -3.3
                },
                'volume_analysis': {'volume_vs_avg_pct': -40},
                'market_state_analysis': {
                    'current_state': 'SIDEWAY',
                    'strategy': {
                        'strategy_name': 'Support/Resistance + RSI Swing',
                        'action_signal': 'READY',
                        'entry_readiness': 60.5
                    },
                    'confidence': {'confidence': 79}
                }
            },
            'fundamental_analysis': {
                'overall_score': 5.7,
                'financial_ratios': {
                    'pe_ratio': 15.3,
                    'debt_to_equity': 0.8,
                    'roe': 12.5,
                    'profit_margin': 8.2
                },
                'insider_analysis': {'summary': 'CEO ขาย $8M'}
            }
        },
        'action_plan': {
            'action_instruction': '💰 เข้าซื้อได้ แต่ระวัง',
            'position_size_recommendation': 'ลดขนาด 50-70%'
        },
        'suggested_entry': 19.47,
        'suggested_stop_loss': 18.98,
        'suggested_targets': [20.16],
        'risk_reward_ratio': 1.40
    }

    service = AISecondOpinion()
    result = service.analyze(mock_results)

    if result['success']:
        print("✅ AI Second Opinion generated successfully!")
        opinion = result['ai_second_opinion']
        print(f"\nVerdict: {opinion.get('verdict_message', 'N/A')}")
        print(f"Confidence: {opinion.get('ai_confidence', 0)}%")
        print(f"\nRecommendation: {opinion.get('recommendation', {}).get('primary_action', 'N/A')}")
    else:
        print(f"❌ Failed: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
