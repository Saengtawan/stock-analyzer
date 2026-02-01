#!/usr/bin/env python3
"""
Stock Analyzer with Local LLM
=============================

AI-powered stock analysis using local LLM (Ollama).
Provides intelligent analysis beyond rule-based systems.

Features:
- Technical analysis interpretation
- News sentiment analysis
- Entry/Exit recommendations
- Risk assessment
- Second opinion before trades
"""

import os
import sys
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from local_llm.ollama_client import OllamaClient, LLMResponse


@dataclass
class StockAnalysis:
    """Complete stock analysis result"""
    symbol: str
    recommendation: str  # BUY, SELL, HOLD, AVOID
    confidence: int  # 0-100
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    risk_level: str  # LOW, MEDIUM, HIGH, EXTREME
    reasoning: str
    key_factors: List[str]
    warnings: List[str]
    analysis_time: float


class StockAnalyzerLLM:
    """
    AI Stock Analyzer using Local LLM

    Usage:
        analyzer = StockAnalyzerLLM()
        result = analyzer.analyze_stock("NVDA", price=140, rsi=65, trend="up")
        print(result.recommendation)
    """

    SYSTEM_PROMPT = """You are an expert stock analyst with 20+ years of experience.
You analyze stocks based on technical indicators, fundamentals, and market conditions.

Your analysis style:
- Data-driven and objective
- Clear buy/sell recommendations with specific prices
- Risk-aware with stop-loss suggestions
- Concise but comprehensive

Always provide:
1. Clear recommendation (BUY/SELL/HOLD/AVOID)
2. Confidence level (0-100%)
3. Entry price, Stop Loss, Take Profit
4. Risk assessment
5. Key factors driving the recommendation
6. Any warnings or concerns

Be honest about uncertainty. If data is insufficient, say so."""

    ANALYSIS_TEMPLATE = """Analyze this stock for potential trade:

**{symbol}** - Current Price: ${price:.2f}

Technical Indicators:
- RSI (14): {rsi:.1f}
- Price vs SMA20: {sma20_status}
- Price vs SMA50: {sma50_status}
- ATR (volatility): ${atr:.2f} ({atr_pct:.1f}%)
- Volume: {volume_status}
- Trend: {trend}

Support/Resistance:
- Nearest Support: ${support:.2f}
- Nearest Resistance: ${resistance:.2f}

Market Context:
- Market Regime: {market_regime}
- Sector: {sector}
- Sector Regime: {sector_regime}

{additional_context}

Based on this data, provide your analysis in this format:
RECOMMENDATION: [BUY/SELL/HOLD/AVOID]
CONFIDENCE: [0-100]%
ENTRY: $[price] (or "current" or "wait for pullback to $X")
STOP_LOSS: $[price]
TAKE_PROFIT: $[price]
RISK_LEVEL: [LOW/MEDIUM/HIGH/EXTREME]

REASONING:
[2-3 sentences explaining your recommendation]

KEY_FACTORS:
- [Factor 1]
- [Factor 2]
- [Factor 3]

WARNINGS:
- [Warning 1 if any]
- [Warning 2 if any]"""

    def __init__(self, model: str = "llama3.2:1b"):
        """
        Initialize Stock Analyzer

        Args:
            model: Ollama model to use
        """
        self.client = OllamaClient(default_model=model)
        self.model = model

        if not self.client.is_available():
            logger.warning("⚠️ Ollama not available - LLM analysis disabled")
            self.available = False
        else:
            self.available = True
            logger.info(f"✅ StockAnalyzerLLM initialized with {model}")

    def is_available(self) -> bool:
        """Check if LLM is available"""
        return self.available and self.client.is_available()

    def analyze_stock(self,
                      symbol: str,
                      price: float,
                      rsi: float = 50,
                      atr: float = None,
                      sma20: float = None,
                      sma50: float = None,
                      support: float = None,
                      resistance: float = None,
                      volume_ratio: float = 1.0,
                      trend: str = "neutral",
                      market_regime: str = "NEUTRAL",
                      sector: str = "Unknown",
                      sector_regime: str = "NEUTRAL",
                      additional_context: str = "") -> Optional[StockAnalysis]:
        """
        Analyze a stock using LLM

        Args:
            symbol: Stock symbol
            price: Current price
            rsi: RSI value
            atr: Average True Range
            sma20: 20-day SMA
            sma50: 50-day SMA
            support: Nearest support level
            resistance: Nearest resistance level
            volume_ratio: Current volume vs average
            trend: Price trend (up/down/neutral)
            market_regime: Market condition
            sector: Stock sector
            sector_regime: Sector condition
            additional_context: Any extra info

        Returns:
            StockAnalysis or None if failed
        """
        if not self.is_available():
            logger.warning("LLM not available")
            return None

        # Calculate derived values
        atr = atr or price * 0.025  # Default 2.5% ATR
        atr_pct = (atr / price) * 100
        sma20 = sma20 or price
        sma50 = sma50 or price
        support = support or price * 0.95
        resistance = resistance or price * 1.05

        # Status strings
        sma20_status = f"{'above' if price > sma20 else 'below'} (${sma20:.2f})"
        sma50_status = f"{'above' if price > sma50 else 'below'} (${sma50:.2f})"

        if volume_ratio > 1.5:
            volume_status = f"HIGH ({volume_ratio:.1f}x average)"
        elif volume_ratio > 1.0:
            volume_status = f"Above average ({volume_ratio:.1f}x)"
        elif volume_ratio > 0.7:
            volume_status = f"Normal ({volume_ratio:.1f}x)"
        else:
            volume_status = f"LOW ({volume_ratio:.1f}x average)"

        # Build prompt
        prompt = self.ANALYSIS_TEMPLATE.format(
            symbol=symbol,
            price=price,
            rsi=rsi,
            sma20_status=sma20_status,
            sma50_status=sma50_status,
            atr=atr,
            atr_pct=atr_pct,
            volume_status=volume_status,
            trend=trend,
            support=support,
            resistance=resistance,
            market_regime=market_regime,
            sector=sector,
            sector_regime=sector_regime,
            additional_context=additional_context or "No additional context."
        )

        # Get LLM response
        start_time = datetime.now()
        response = self.client.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,  # Lower temperature for more consistent analysis
            max_tokens=1024
        )

        if not response.success:
            logger.error(f"LLM failed: {response.error}")
            return None

        # Parse response
        analysis = self._parse_analysis(
            symbol=symbol,
            response_text=response.content,
            current_price=price,
            analysis_time=response.generation_time
        )

        return analysis

    def _parse_analysis(self,
                        symbol: str,
                        response_text: str,
                        current_price: float,
                        analysis_time: float) -> StockAnalysis:
        """Parse LLM response into structured analysis"""

        # Default values
        recommendation = "HOLD"
        confidence = 50
        entry_price = current_price
        stop_loss = current_price * 0.95
        take_profit = current_price * 1.10
        risk_level = "MEDIUM"
        reasoning = response_text
        key_factors = []
        warnings = []

        lines = response_text.split('\n')

        for line in lines:
            line = line.strip()
            upper_line = line.upper()

            # Parse recommendation
            if upper_line.startswith('RECOMMENDATION:'):
                rec = line.split(':', 1)[1].strip().upper()
                if 'BUY' in rec:
                    recommendation = 'BUY'
                elif 'SELL' in rec:
                    recommendation = 'SELL'
                elif 'AVOID' in rec:
                    recommendation = 'AVOID'
                else:
                    recommendation = 'HOLD'

            # Parse confidence
            elif upper_line.startswith('CONFIDENCE:'):
                try:
                    conf_str = line.split(':', 1)[1].strip().replace('%', '')
                    confidence = int(float(conf_str))
                    confidence = max(0, min(100, confidence))
                except:
                    pass

            # Parse entry
            elif upper_line.startswith('ENTRY:'):
                try:
                    entry_str = line.split(':', 1)[1].strip()
                    if 'current' in entry_str.lower():
                        entry_price = current_price
                    else:
                        # Extract number
                        import re
                        nums = re.findall(r'\d+\.?\d*', entry_str)
                        if nums:
                            entry_price = float(nums[0])
                except:
                    pass

            # Parse stop loss
            elif upper_line.startswith('STOP_LOSS:') or upper_line.startswith('STOP LOSS:'):
                try:
                    import re
                    nums = re.findall(r'\d+\.?\d*', line)
                    if nums:
                        stop_loss = float(nums[0])
                except:
                    pass

            # Parse take profit
            elif upper_line.startswith('TAKE_PROFIT:') or upper_line.startswith('TAKE PROFIT:'):
                try:
                    import re
                    nums = re.findall(r'\d+\.?\d*', line)
                    if nums:
                        take_profit = float(nums[0])
                except:
                    pass

            # Parse risk level
            elif upper_line.startswith('RISK_LEVEL:') or upper_line.startswith('RISK LEVEL:'):
                risk_str = line.split(':', 1)[1].strip().upper()
                if 'EXTREME' in risk_str:
                    risk_level = 'EXTREME'
                elif 'HIGH' in risk_str:
                    risk_level = 'HIGH'
                elif 'LOW' in risk_str:
                    risk_level = 'LOW'
                else:
                    risk_level = 'MEDIUM'

            # Parse key factors
            elif line.startswith('- ') and 'KEY_FACTORS' in response_text.upper():
                # Check if we're in the key factors section
                key_idx = response_text.upper().find('KEY_FACTORS')
                warn_idx = response_text.upper().find('WARNING')
                line_idx = response_text.find(line)

                if key_idx < line_idx < (warn_idx if warn_idx > 0 else len(response_text)):
                    key_factors.append(line[2:].strip())

            # Parse warnings
            elif line.startswith('- ') and 'WARNING' in response_text.upper():
                warn_idx = response_text.upper().find('WARNING')
                line_idx = response_text.find(line)

                if line_idx > warn_idx:
                    warnings.append(line[2:].strip())

        # Extract reasoning if not parsed
        if 'REASONING:' in response_text.upper():
            try:
                idx = response_text.upper().find('REASONING:')
                end_idx = response_text.upper().find('KEY_FACTORS')
                if end_idx == -1:
                    end_idx = len(response_text)
                reasoning = response_text[idx+10:end_idx].strip()
            except:
                pass

        return StockAnalysis(
            symbol=symbol,
            recommendation=recommendation,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_level=risk_level,
            reasoning=reasoning[:500] if len(reasoning) > 500 else reasoning,
            key_factors=key_factors[:5],
            warnings=warnings[:3],
            analysis_time=analysis_time
        )

    def get_second_opinion(self,
                           symbol: str,
                           current_analysis: Dict,
                           proposed_action: str) -> Dict:
        """
        Get a second opinion on a proposed trade

        Args:
            symbol: Stock symbol
            current_analysis: Existing analysis data
            proposed_action: "BUY" or "SELL"

        Returns:
            Dict with agree/disagree and reasoning
        """
        if not self.is_available():
            return {"available": False, "error": "LLM not available"}

        prompt = f"""I'm about to {proposed_action} {symbol}. Here's my analysis:

Current Price: ${current_analysis.get('price', 'N/A')}
Entry: ${current_analysis.get('entry', 'N/A')}
Stop Loss: ${current_analysis.get('stop_loss', 'N/A')}
Take Profit: ${current_analysis.get('take_profit', 'N/A')}
RSI: {current_analysis.get('rsi', 'N/A')}
Trend: {current_analysis.get('trend', 'N/A')}

Do you agree with this trade? Respond in this format:
AGREE: YES or NO
CONFIDENCE: [0-100]%
REASONING: [1-2 sentences]
SUGGESTION: [Any modification to improve the trade]"""

        response = self.client.generate(
            prompt=prompt,
            system_prompt="You are a risk-conscious trading advisor. Be skeptical and protective of capital.",
            temperature=0.4
        )

        if not response.success:
            return {"available": False, "error": response.error}

        # Parse response
        text = response.content
        agree = "YES" in text.upper().split("AGREE")[1][:20] if "AGREE" in text.upper() else None

        return {
            "available": True,
            "agree": agree,
            "full_response": text,
            "generation_time": response.generation_time
        }

    def analyze_news_sentiment(self, symbol: str, headlines: List[str]) -> Dict:
        """
        Analyze news headlines for sentiment

        Args:
            symbol: Stock symbol
            headlines: List of news headlines

        Returns:
            Dict with sentiment score and analysis
        """
        if not self.is_available():
            return {"available": False, "error": "LLM not available"}

        if not headlines:
            return {"available": True, "sentiment": "NEUTRAL", "score": 0}

        headlines_text = "\n".join([f"- {h}" for h in headlines[:10]])

        prompt = f"""Analyze these news headlines for {symbol}:

{headlines_text}

Provide sentiment analysis:
SENTIMENT: [VERY_BULLISH/BULLISH/NEUTRAL/BEARISH/VERY_BEARISH]
SCORE: [-100 to +100]
SUMMARY: [1 sentence summary of news impact]
KEY_NEWS: [Most important headline and why]"""

        response = self.client.generate(
            prompt=prompt,
            system_prompt="You are a financial news analyst. Focus on how news affects stock prices.",
            temperature=0.3
        )

        if not response.success:
            return {"available": False, "error": response.error}

        # Parse sentiment
        text = response.content.upper()
        if 'VERY_BULLISH' in text or 'VERY BULLISH' in text:
            sentiment = 'VERY_BULLISH'
            score = 80
        elif 'BULLISH' in text:
            sentiment = 'BULLISH'
            score = 40
        elif 'VERY_BEARISH' in text or 'VERY BEARISH' in text:
            sentiment = 'VERY_BEARISH'
            score = -80
        elif 'BEARISH' in text:
            sentiment = 'BEARISH'
            score = -40
        else:
            sentiment = 'NEUTRAL'
            score = 0

        return {
            "available": True,
            "sentiment": sentiment,
            "score": score,
            "full_response": response.content,
            "generation_time": response.generation_time
        }


def test_analyzer():
    """Test the stock analyzer"""
    print("=" * 60)
    print("Testing StockAnalyzerLLM")
    print("=" * 60)

    analyzer = StockAnalyzerLLM()

    if not analyzer.is_available():
        print("❌ LLM not available!")
        print()
        print("To enable LLM analysis:")
        print("  1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh")
        print("  2. Start Ollama: ollama serve")
        print("  3. Pull model: ollama pull llama3.2:3b")
        return

    print("✅ LLM available")
    print()
    print("Analyzing NVDA...")

    result = analyzer.analyze_stock(
        symbol="NVDA",
        price=140.0,
        rsi=58,
        atr=5.2,
        sma20=135.0,
        sma50=130.0,
        support=132.0,
        resistance=150.0,
        volume_ratio=1.3,
        trend="uptrend",
        market_regime="BULL",
        sector="Technology",
        sector_regime="STRONG BULL"
    )

    if result:
        print()
        print(f"📊 Analysis Result for {result.symbol}")
        print("-" * 40)
        print(f"Recommendation: {result.recommendation}")
        print(f"Confidence: {result.confidence}%")
        print(f"Entry: ${result.entry_price:.2f}")
        print(f"Stop Loss: ${result.stop_loss:.2f}")
        print(f"Take Profit: ${result.take_profit:.2f}")
        print(f"Risk Level: {result.risk_level}")
        print()
        print(f"Reasoning: {result.reasoning[:200]}...")
        print()
        print(f"Key Factors: {result.key_factors}")
        print(f"Warnings: {result.warnings}")
        print()
        print(f"Analysis Time: {result.analysis_time:.2f}s")
    else:
        print("❌ Analysis failed")


if __name__ == "__main__":
    test_analyzer()
