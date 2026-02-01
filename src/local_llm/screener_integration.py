#!/usr/bin/env python3
"""
Screener Integration with Local LLM
====================================

Integrates Local LLM analysis into the stock screening pipeline.
Provides AI-enhanced filtering and analysis for draft picks.

Features:
- AI pre-filter before adding to drafts
- Second opinion on screener picks
- News sentiment integration
- Risk-adjusted recommendations
"""

import os
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from loguru import logger
import yfinance as yf
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from local_llm.ollama_client import OllamaClient
from local_llm.stock_analyzer_llm import StockAnalyzerLLM, StockAnalysis


class LLMScreenerIntegration:
    """
    AI-Enhanced Stock Screener

    Adds LLM analysis layer to existing screeners for smarter picks.
    """

    def __init__(self, model: str = "llama3.2:1b"):
        """
        Initialize LLM Screener Integration

        Args:
            model: Ollama model to use
        """
        self.analyzer = StockAnalyzerLLM(model=model)
        self.available = self.analyzer.is_available()

        if self.available:
            logger.info("✅ LLM Screener Integration enabled")
        else:
            logger.warning("⚠️ LLM not available - using rule-based only")

    def analyze_candidate(self,
                          symbol: str,
                          screener_data: Dict) -> Tuple[bool, Dict]:
        """
        Analyze a screener candidate with LLM

        Args:
            symbol: Stock symbol
            screener_data: Data from screener (price, indicators, etc.)

        Returns:
            (should_include, analysis_data)
        """
        if not self.available:
            return True, {"llm_available": False}

        # Get additional data
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="90d")

            if hist.empty:
                return True, {"llm_available": False, "error": "No price data"}

            # Calculate indicators
            close = hist['Close']
            high = hist['High']
            low = hist['Low']
            volume = hist['Volume']

            current_price = float(close.iloc[-1])

            # RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = float(100 - (100 / (1 + rs.iloc[-1])))

            # ATR
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = np.maximum(np.maximum(tr1, tr2), tr3)
            atr = float(tr.rolling(14).mean().iloc[-1])

            # SMAs
            sma20 = float(close.rolling(20).mean().iloc[-1])
            sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else sma20

            # Support/Resistance
            support = float(low.rolling(20).min().iloc[-1])
            resistance = float(high.rolling(20).max().iloc[-1])

            # Volume ratio
            avg_volume = float(volume.rolling(20).mean().iloc[-1])
            current_volume = float(volume.iloc[-1])
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            # Trend
            if current_price > sma20 > sma50:
                trend = "strong uptrend"
            elif current_price > sma20:
                trend = "uptrend"
            elif current_price < sma20 < sma50:
                trend = "strong downtrend"
            elif current_price < sma20:
                trend = "downtrend"
            else:
                trend = "neutral"

        except Exception as e:
            logger.error(f"Error getting data for {symbol}: {e}")
            return True, {"llm_available": False, "error": str(e)}

        # Get LLM analysis
        analysis = self.analyzer.analyze_stock(
            symbol=symbol,
            price=current_price,
            rsi=rsi,
            atr=atr,
            sma20=sma20,
            sma50=sma50,
            support=support,
            resistance=resistance,
            volume_ratio=volume_ratio,
            trend=trend,
            market_regime=screener_data.get('market_regime', 'NEUTRAL'),
            sector=screener_data.get('sector', 'Unknown'),
            sector_regime=screener_data.get('sector_regime', 'NEUTRAL'),
            additional_context=screener_data.get('context', '')
        )

        if not analysis:
            return True, {"llm_available": False, "error": "Analysis failed"}

        # Decision logic
        should_include = True
        reasons = []

        # Reject if LLM says AVOID with high confidence
        if analysis.recommendation == 'AVOID' and analysis.confidence >= 70:
            should_include = False
            reasons.append(f"LLM recommends AVOID ({analysis.confidence}% confidence)")

        # Reject if risk is EXTREME
        if analysis.risk_level == 'EXTREME':
            should_include = False
            reasons.append("Risk level: EXTREME")

        # Boost if LLM says BUY with high confidence
        boost = 0
        if analysis.recommendation == 'BUY' and analysis.confidence >= 70:
            boost = 20
            reasons.append(f"LLM recommends BUY ({analysis.confidence}% confidence)")

        return should_include, {
            "llm_available": True,
            "recommendation": analysis.recommendation,
            "confidence": analysis.confidence,
            "entry_price": analysis.entry_price,
            "stop_loss": analysis.stop_loss,
            "take_profit": analysis.take_profit,
            "risk_level": analysis.risk_level,
            "reasoning": analysis.reasoning,
            "key_factors": analysis.key_factors,
            "warnings": analysis.warnings,
            "analysis_time": analysis.analysis_time,
            "should_include": should_include,
            "filter_reasons": reasons,
            "score_boost": boost
        }

    def filter_candidates(self,
                          candidates: List[Dict],
                          max_analyze: int = 20) -> List[Dict]:
        """
        Filter a list of screener candidates using LLM

        Args:
            candidates: List of candidate stocks from screener
            max_analyze: Maximum candidates to analyze (LLM is slow)

        Returns:
            Filtered and enhanced candidate list
        """
        if not self.available:
            logger.warning("LLM not available - returning unfiltered candidates")
            return candidates

        logger.info(f"🤖 LLM analyzing {min(len(candidates), max_analyze)} candidates...")

        filtered = []
        rejected = []

        for i, candidate in enumerate(candidates[:max_analyze]):
            symbol = candidate.get('symbol', candidate.get('ticker', ''))
            if not symbol:
                continue

            logger.info(f"  [{i+1}/{min(len(candidates), max_analyze)}] Analyzing {symbol}...")

            should_include, analysis = self.analyze_candidate(symbol, candidate)

            # Merge analysis into candidate
            enhanced = {**candidate, **analysis}

            if should_include:
                # Adjust score with LLM boost
                if 'score' in enhanced and 'score_boost' in analysis:
                    enhanced['original_score'] = enhanced['score']
                    enhanced['score'] = enhanced['score'] + analysis.get('score_boost', 0)

                filtered.append(enhanced)
            else:
                enhanced['rejected_reason'] = analysis.get('filter_reasons', ['LLM filtered'])
                rejected.append(enhanced)

        # Sort by enhanced score
        filtered.sort(key=lambda x: x.get('score', 0), reverse=True)

        logger.info(f"✅ LLM Filter: {len(filtered)} passed, {len(rejected)} rejected")

        if rejected:
            logger.info("Rejected stocks:")
            for r in rejected[:5]:
                logger.info(f"  ❌ {r.get('symbol')}: {r.get('rejected_reason')}")

        return filtered

    def get_trade_confirmation(self,
                               symbol: str,
                               entry_price: float,
                               stop_loss: float,
                               take_profit: float) -> Dict:
        """
        Get LLM confirmation before executing a trade

        Args:
            symbol: Stock symbol
            entry_price: Planned entry price
            stop_loss: Planned stop loss
            take_profit: Planned take profit

        Returns:
            Confirmation result with agree/disagree and reasoning
        """
        if not self.available:
            return {
                "available": False,
                "proceed": True,
                "message": "LLM not available - proceeding without confirmation"
            }

        analysis = {
            'price': entry_price,
            'entry': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
        }

        result = self.analyzer.get_second_opinion(
            symbol=symbol,
            current_analysis=analysis,
            proposed_action="BUY"
        )

        if not result.get('available', False):
            return {
                "available": False,
                "proceed": True,
                "message": "Could not get LLM opinion - proceeding"
            }

        proceed = result.get('agree', True)

        return {
            "available": True,
            "proceed": proceed,
            "agree": result.get('agree'),
            "reasoning": result.get('full_response', ''),
            "generation_time": result.get('generation_time', 0)
        }


class LLMDraftEnhancer:
    """
    Enhances draft stocks with LLM analysis
    """

    def __init__(self, model: str = "llama3.2:1b"):
        self.integration = LLMScreenerIntegration(model=model)

    def enhance_drafts(self, drafts: List[Dict]) -> List[Dict]:
        """
        Add LLM analysis to draft stocks

        Args:
            drafts: List of draft stocks

        Returns:
            Enhanced drafts with LLM analysis
        """
        if not self.integration.available:
            return drafts

        enhanced = []
        for draft in drafts:
            symbol = draft.get('symbol', '')
            if not symbol:
                enhanced.append(draft)
                continue

            _, analysis = self.integration.analyze_candidate(symbol, draft)

            enhanced_draft = {
                **draft,
                'llm_analysis': analysis
            }

            # Add LLM-suggested SL/TP if available
            if analysis.get('llm_available', False):
                enhanced_draft['llm_entry'] = analysis.get('entry_price')
                enhanced_draft['llm_stop_loss'] = analysis.get('stop_loss')
                enhanced_draft['llm_take_profit'] = analysis.get('take_profit')
                enhanced_draft['llm_recommendation'] = analysis.get('recommendation')
                enhanced_draft['llm_confidence'] = analysis.get('confidence')
                enhanced_draft['llm_risk'] = analysis.get('risk_level')

            enhanced.append(enhanced_draft)

        return enhanced


def test_integration():
    """Test the integration"""
    print("=" * 60)
    print("Testing LLM Screener Integration")
    print("=" * 60)

    integration = LLMScreenerIntegration()

    if not integration.available:
        print("❌ LLM not available!")
        print()
        print("Setup instructions:")
        print("  1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh")
        print("  2. Start Ollama: ollama serve")
        print("  3. Pull model: ollama pull llama3.2:3b")
        return

    print("✅ LLM available")
    print()

    # Test single candidate
    print("Testing single candidate analysis (NVDA)...")

    should_include, analysis = integration.analyze_candidate(
        symbol="NVDA",
        screener_data={
            "market_regime": "BULL",
            "sector": "Technology",
            "sector_regime": "STRONG BULL"
        }
    )

    print(f"Should include: {should_include}")
    print(f"Recommendation: {analysis.get('recommendation')}")
    print(f"Confidence: {analysis.get('confidence')}%")
    print(f"Risk Level: {analysis.get('risk_level')}")
    print(f"Entry: ${analysis.get('entry_price', 0):.2f}")
    print(f"Stop Loss: ${analysis.get('stop_loss', 0):.2f}")
    print(f"Take Profit: ${analysis.get('take_profit', 0):.2f}")
    print()

    # Test batch filtering
    print("Testing batch filtering...")

    candidates = [
        {"symbol": "NVDA", "score": 80},
        {"symbol": "AMD", "score": 75},
        {"symbol": "AAPL", "score": 70},
    ]

    filtered = integration.filter_candidates(candidates, max_analyze=3)

    print(f"Filtered candidates: {len(filtered)}")
    for c in filtered:
        print(f"  {c['symbol']}: score={c.get('score')} rec={c.get('recommendation')}")


if __name__ == "__main__":
    test_integration()
