#!/usr/bin/env python3
"""
AI Universe Generator
ใช้ DeepSeek AI generate stock universe แบบ real-time สำหรับ screening
"""

import json
import re
import os
from typing import List, Dict, Any, Optional
from loguru import logger
from deepseek_service import deepseek_service


class AIUniverseGenerator:
    """Generate stock universe using AI for dynamic screening"""

    def __init__(self):
        """Initialize AI Universe Generator"""
        self.deepseek_service = deepseek_service

    def generate_dividend_universe(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Generate comprehensive dividend stock universe using AI

        Args:
            criteria: User criteria for dividend screening

        Returns:
            List of stock symbols for dividend screening
        """
        try:
            min_yield = criteria.get('min_dividend_yield', 3.0)
            max_stocks = criteria.get('max_stocks', 15)

            # Adjust universe size to 3x max_stocks for optimal screening efficiency
            universe_size = max_stocks * 3

            prompt = f"""You are an experienced dividend stock analyst with expertise in quantitative metrics and current market data. Generate a focused universe of {universe_size} dividend stocks and ETFs using DATA CURRENT AS OF 2024-2025 timeframe for screening and selection.

CRITICAL TIME HORIZON AND DATA FRESHNESS REQUIREMENTS:
- MUST select companies that CURRENTLY STILL PAY DIVIDENDS as of 2024-2025
- Use most recent financial data and dividend payment records
- Exclude companies that have suspended or eliminated dividends in 2023-2024
- Verify dividend payment continuity through recent market cycles
- Focus on companies with recent quarterly dividend declarations

HIGH-YIELD ETF PRIORITY REQUIREMENTS:
- MANDATORY INCLUSION: High-yield dividend ETFs with yields >8%
- Required ETFs: QQQI (Invesco QQQT Nasdaq-100 Covered Call ETF), SPYI (SPDR S&P 500 High Dividend ETF), JEPQ (JPMorgan Equity Premium Income ETF), QYLD (Global X NASDAQ 100 Covered Call ETF), JEPI (JPMorgan Equity Premium Income ETF)
- Additional high-yield ETFs: SCHD, VYM, DVY, HDV, NOBL, VIG, SPHD, DGRO
- ETF yield range: 6% to 15% (include high-yield covered call and income strategies)
- ETF allocation: Minimum 35% of universe must be dividend-focused ETFs

QUANTITATIVE DIVIDEND SCREENING CRITERIA (METRIC-BASED ONLY):
- Current dividend yield: {min_yield}% minimum to 15.0% maximum (expanded for high-yield ETFs)
- Payout ratio: 30% minimum to 75% maximum for individual stocks (ETFs can exceed)
- Dividend growth rate: minimum 3% average over last 5 years (individual stocks)
- Free cash flow coverage: minimum 1.5x dividend payments (individual stocks)
- Years of consecutive dividend payments: minimum 5 years uninterrupted

FINANCIAL QUALITY METRICS (SPECIFIC THRESHOLDS):
- Revenue growth: minimum -5% to avoid declining businesses
- Return on Equity (ROE): minimum 10% over last 3 years average
- Debt-to-Equity ratio: maximum 1.0 for utilities, 0.7 for others
- Interest coverage ratio: minimum 3.0x EBITDA/Interest
- Current ratio: minimum 1.2 for liquidity assessment

MARKET AND LIQUIDITY STANDARDS:
- Average daily trading volume: minimum 500K shares (stocks), 100K (ETFs)
- Market capitalization: minimum $1B for individual stocks
- Share price range: $5 to $500 (exclude penny stocks and extreme high-price)
- Minimum 1-year trading history (no recent IPOs)
- Institutional ownership: minimum 25%

SECTOR ALLOCATION AND DIVERSIFICATION REQUIREMENTS:
- Maximum 20% allocation per sector to ensure diversification
- Required sectors: Utilities (10%), Consumer Staples (10%), Healthcare (10%)
- Discretionary sectors: Financials (15%), REITs (10%), Energy (10%), Others (10%)
- Asset class mix: 65% individual dividend stocks, 35% dividend-focused ETFs
- Geographic focus: 80% US securities, 20% international dividend opportunities

EXCLUSION CRITERIA (STRICT):
- No companies with dividend cuts in last 24 months
- No meme stocks or highly volatile speculative securities
- No companies under bankruptcy proceedings or delisting warnings
- No companies with negative free cash flow for 2+ consecutive quarters
- No companies with payout ratios above 85% (individual stocks only)

FINAL SELECTION VALIDATION:
- Verify that high-yield ETFs (QQQI, SPYI, JEPQ, QYLD, JEPI) are included
- Ensure ETF allocation is at least 35% of total universe
- Include both income-focused and covered call strategy ETFs
- Balance between high-yield (>8%) and moderate-yield (4-8%) securities

Select securities based ONLY on these quantitative metrics. Avoid subjective assessments like "competitive advantages" or "high-quality" without specific measurable criteria.

Return ONLY a valid JSON array of ticker symbols, no explanations or comments:
["SYMBOL1", "SYMBOL2", "SYMBOL3", ...]"""

            logger.info(f"Generating dividend universe with criteria: min_yield={min_yield}%, size={universe_size}")

            # Call DeepSeek API to generate real universe
            response = self._call_deepseek_api(prompt)
            if response:
                symbols = self._parse_symbols_from_response(response)
                if symbols and len(symbols) >= 10:  # At least 10 symbols
                    logger.info(f"✅ DeepSeek generated {len(symbols)} dividend symbols")
                    return symbols[:universe_size]
                else:
                    logger.error("DeepSeek response had insufficient symbols. AI-only system.")
                    raise ValueError("AI universe generation failed. Cannot proceed without AI.")

            # No fallback - AI-only system
            logger.error("DeepSeek API failed for dividend universe generation. No fallback available.")
            raise ValueError("AI universe generation failed. Cannot proceed without AI.")

        except Exception as e:
            logger.error(f"Failed to generate dividend universe: {e}")
            raise ValueError(f"AI universe generation failed: {e}")

    def generate_support_level_universe(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Generate comprehensive stock universe for support level screening

        Args:
            criteria: User criteria for support level screening

        Returns:
            List of stock symbols for technical analysis
        """
        try:
            max_stocks = criteria.get('max_stocks', 10)
            time_horizon = criteria.get('time_horizon', 'medium')
            max_distance_from_support = criteria.get('max_distance_from_support', 0.05)

            # Adjust universe size to 3x max_stocks for optimal screening efficiency
            universe_size = max_stocks * 3

            prompt = f"""You are an experienced technical analyst and quantitative trader. Generate a carefully curated universe of {universe_size} stocks and ETFs optimized for support level screening with current prices within {max_distance_from_support*100:.1f}% of key support levels.

TARGET SCREENING CRITERIA:
- Current prices should be at or near major support levels
- Maximum distance from support: {max_distance_from_support*100:.1f}% below support
- Focus on stocks showing POTENTIAL BOUNCE SIGNALS from support areas
- Prioritize securities with recent bullish reversal patterns near support

TIMEFRAME AND SUPPORT/RESISTANCE IDENTIFICATION:
- Primary timeframe: Daily charts for {time_horizon} term analysis
- Support levels defined by: Swing lows from last 20-50 candles
- Additional confirmation from: 50/200 SMA levels, Fibonacci retracements
- Volume profile and VWAP support zones consideration
- Historical significance: At least 2-3 prior bounces from support level

TECHNICAL SIGNAL FILTERING:
- Bullish candlestick patterns near support (hammer, doji, engulfing patterns)
- RSI < 40 showing oversold conditions with potential upward turn
- MACD histogram showing signs of improvement near support
- Volume confirmation: Higher volume on recent support tests
- Price action: Clean bounces, not just touching support

LIQUIDITY AND MARKET CAP REQUIREMENTS:
- Minimum average daily volume: 1M shares (stocks) / 100K shares (ETFs)
- Market cap: Minimum $500M for individual stocks
- Price range: $5-$500 per share (avoid penny stocks and extreme high-price)
- No recent IPOs (minimum 1 year trading history)
- Exclude low-float stocks prone to manipulation

VOLATILITY AND BETA CONSTRAINTS:
- Beta range: 0.5 to 2.0 (avoid extremely volatile or dormant stocks)
- Average True Range (ATR): 2-8% for meaningful support/resistance levels
- Avoid stocks with excessive gap trading or erratic price action
- Prefer securities with consistent intraday trading patterns

RISK MANAGEMENT AND QUALITY FILTERS:
- Clean price action: No frequent gaps, smooth trend progression
- Institutional ownership: Minimum 30% institutional holding
- Analyst coverage: At least 3 analysts covering the stock
- Financial stability: No recent bankruptcy or delisting warnings
- Exclude meme stocks with artificial price manipulation

UNIVERSE COMPOSITION AND SECTOR DIVERSIFICATION:
- Maximum 3-4 stocks per sector to ensure diversification
- Diverse sector representation: Technology, Healthcare, Financials, Consumer, Energy, etc.
- Mix of individual stocks (70%) and liquid ETFs (30%)
- Include both growth and value oriented securities
- Balance between momentum and mean-reversion candidates
- Geographic mix: 80% US stocks, 20% international exposure via ETFs
- Market cap distribution: 50% large-cap, 30% mid-cap, 20% small-cap (>$500M)

FINAL SELECTION CRITERIA:
- Prioritize stocks with multiple technical confirmation signals
- Ensure each selected security has clear risk/reward setup (min 2:1 ratio)
- Focus on securities with upcoming catalysts (earnings, events) that could trigger bounces
- Select stocks where support levels have institutional significance
- Avoid overcrowded trades or overly popular momentum stocks

Use your deep understanding of market microstructure, price behavior, and technical patterns to select securities currently positioned near support levels within the specified {max_distance_from_support*100:.1f}% criteria. Focus on liquid, well-behaved securities that professional technical traders actually trade, showing signs of potential bounce signals from established support zones with clear risk management levels.

Return ONLY a valid JSON array of ticker symbols:
["SYMBOL1", "SYMBOL2", "SYMBOL3", ...]"""

            logger.info(f"Generating support level universe with criteria: time_horizon={time_horizon}, max_distance={max_distance_from_support*100:.1f}%, size={universe_size}")

            # Call DeepSeek API to generate real universe
            response = self._call_deepseek_api(prompt)
            if response:
                symbols = self._parse_symbols_from_response(response)
                if symbols and len(symbols) >= 10:  # At least 10 symbols
                    logger.info(f"✅ DeepSeek generated {len(symbols)} support level symbols")
                    return symbols[:universe_size]
                else:
                    logger.error("DeepSeek response had insufficient symbols. AI-only system.")
                    raise ValueError("AI universe generation failed. Cannot proceed without AI.")

            # No fallback - AI-only system
            logger.error("DeepSeek API failed for support level universe generation. No fallback available.")
            raise ValueError("AI universe generation failed. Cannot proceed without AI.")

        except Exception as e:
            logger.error(f"Failed to generate support level universe: {e}")
            raise ValueError(f"AI universe generation failed: {e}")

    def generate_value_universe(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Generate comprehensive stock universe for value/undervalued growth screening

        Args:
            criteria: User criteria for value screening

        Returns:
            List of stock symbols for value analysis
        """
        try:
            max_stocks = criteria.get('max_stocks', 15)
            screen_type = criteria.get('screen_type', 'value')
            time_horizon = criteria.get('time_horizon', 'long')
            max_pe_ratio = criteria.get('max_pe_ratio', 15.0)
            max_pb_ratio = criteria.get('max_pb_ratio', 3.0)
            min_roe = criteria.get('min_roe', 10.0)

            # Adjust universe size to 3x max_stocks for optimal screening efficiency
            universe_size = max_stocks * 3

            if screen_type == 'undervalued_growth':
                prompt = f"""You are an experienced growth stock analyst specializing in identifying undervalued growth opportunities. Generate a focused universe of {universe_size} stocks and ETFs that represent undervalued growth companies with strong fundamentals and reasonable valuations.

TARGET INVESTMENT PROFILE:
- UNDERVALUED GROWTH STOCKS: Companies with strong growth potential trading below fair value
- Time horizon: {time_horizon} term investment (1-3 years)
- Focus on companies with sustainable competitive advantages and expanding markets
- Balance between growth potential and current valuation attractiveness

FUNDAMENTAL SCREENING CRITERIA (GROWTH-ORIENTED):
- Revenue growth: Minimum 10% annual growth over last 3 years
- Earnings growth: Minimum 15% annual growth potential
- P/E ratio: Maximum {max_pe_ratio*1.5:.1f} (allow higher P/E for growth companies)
- PEG ratio: Maximum 1.5 (Price/Earnings to Growth ratio)
- P/B ratio: Maximum {max_pb_ratio*1.5:.1f} (growth companies can trade at higher P/B)
- Return on Equity (ROE): Minimum {min_roe+5:.1f}% (higher for growth companies)
- Profit margins: Improving or maintaining strong margins (>10%)

GROWTH QUALITY INDICATORS:
- Market opportunity: Companies in expanding markets (tech, healthcare, renewables, etc.)
- Revenue diversification: Multiple revenue streams or geographic markets
- R&D investment: Significant investment in research and development
- Management quality: Strong leadership track record
- Competitive moat: Sustainable competitive advantages

FINANCIAL HEALTH REQUIREMENTS:
- Debt-to-Equity ratio: Maximum 0.7 (moderate leverage acceptable for growth)
- Current ratio: Minimum 1.0 (adequate liquidity)
- Free cash flow: Positive or improving trend
- Interest coverage: Minimum 3x (if debt exists)
- Working capital: Positive and growing

MARKET AND SECTOR FOCUS:
- Technology: Cloud computing, AI, cybersecurity, semiconductors
- Healthcare: Biotech, medical devices, digital health
- Consumer: E-commerce, digital services, sustainable products
- Energy: Renewable energy, battery technology, energy efficiency
- Financials: Fintech, digital banking, payment systems
- Exclude: Utilities, REITs, mature cyclicals, declining industries

VALUATION AND TIMING CRITERIA:
- Recent price pullbacks: Stocks down 20-40% from recent highs
- Fundamental disconnects: Strong fundamentals vs. temporary price weakness
- Market inefficiencies: Overlooked companies with strong growth potential
- Earnings revisions: Positive earnings revision trends
- Technical oversold: Stocks showing signs of bottoming out

LIQUIDITY AND QUALITY STANDARDS:
- Market cap: Minimum $1B for individual stocks
- Average daily volume: Minimum 1M shares
- Analyst coverage: Minimum 3 analysts covering
- Institutional ownership: 30-70% (shows smart money interest)
- Float: Minimum 100M shares (avoid low-float manipulation)

Return ONLY a valid JSON array of ticker symbols:
["SYMBOL1", "SYMBOL2", "SYMBOL3", ...]"""

            else:  # 'value' screening
                prompt = f"""You are an experienced value investor specializing in finding undervalued stocks that meet STRICT quantitative criteria. Generate a focused universe of {universe_size} stocks that currently meet these EXACT screening requirements.

CRITICAL: Only include stocks that CURRENTLY meet ALL of these numerical thresholds as of 2024-2025:

MANDATORY VALUATION CRITERIA (MUST MEET ALL):
- P/E ratio: MAXIMUM {max_pe_ratio:.1f} (exclude anything above this)
- P/B ratio: MAXIMUM {max_pb_ratio:.1f} (exclude anything above this)
- Return on Equity (ROE): MINIMUM {min_roe:.1f}% (exclude anything below this)
- Debt-to-Equity ratio: MAXIMUM 0.8 (exclude anything above this)
- Current price: Must be at recent 52-week lows or significantly discounted

SPECIFIC VALUE CHARACTERISTICS TO TARGET:
- Stocks trading at P/E 8-15 (avoid high P/E even if under {max_pe_ratio:.1f})
- P/B ratios 0.5-2.5 (look for below book value opportunities)
- ROE 10-25% (profitable but not overpriced growth)
- Companies with temporary earnings dips but strong underlying business
- Recent price declines due to cyclical factors, not fundamental issues

FOCUS SECTORS FOR VALUE OPPORTUNITIES:
- Regional Banks: Well-capitalized banks with P/E < 12, P/B < 1.5
- Energy: Integrated oil companies, refiners with stable dividends
- Industrials: Machinery, aerospace, defense contractors
- Materials: Steel, chemical companies during downcycles
- Telecom: Mature telecom with high dividend yields
- Consumer Staples: Food/beverage companies during temporary weakness
- Real Estate: REITs trading below NAV
- Value ETFs: Specifically value-focused ETFs (VTV, VTI, VOOV, MTUM, etc.)

EXAMPLES OF VALUE STOCK TYPES TO INCLUDE:
- Banks like KeyCorp (KEY), Fifth Third (FITB), Regions Financial (RF)
- Energy like Exxon (XOM), Chevron (CVX), ConocoPhillips (COP)
- Industrials like Caterpillar (CAT), 3M (MMM), Boeing (BA)
- Telecom like AT&T (T), Verizon (VZ)
- Materials like DowDuPont (DOW), LyondellBasell (LYB)
- Consumer like Kraft Heinz (KHC), General Mills (GIS)
- Value ETFs like VTV, VTI, VOOV, SCHV, VTEB

EXCLUDE HIGH-PRICED QUALITY STOCKS:
- Do NOT include: Apple, Microsoft, Google, Amazon, Tesla, Nvidia
- Do NOT include: Johnson & Johnson, Procter & Gamble, Coca-Cola if P/E > 20
- Do NOT include: Any stock with P/E > {max_pe_ratio:.1f} or P/B > {max_pb_ratio:.1f}
- Do NOT include: High-growth companies trading at premium valuations

MARKET AND LIQUIDITY STANDARDS:
- Market cap: Minimum $1B for individual stocks
- Average daily volume: Minimum 500K shares
- Established companies: Minimum 10 years of trading history
- No recent IPOs or SPACs
- Focus on NYSE/NASDAQ listed securities

CURRENT MARKET CONDITIONS (2024-2025):
- Interest rate environment: Look for rate-sensitive sectors that are discounted
- Post-pandemic recovery: Companies that haven't fully recovered valuation-wise
- Inflation impact: Companies with pricing power but temporarily depressed margins

Select stocks that a disciplined value investor would actually buy today based on Graham's principles of buying below intrinsic value with a margin of safety.

Return ONLY a valid JSON array of ticker symbols:
["SYMBOL1", "SYMBOL2", "SYMBOL3", ...]"""

            logger.info(f"Generating {screen_type} universe with criteria: max_pe={max_pe_ratio}, max_pb={max_pb_ratio}, min_roe={min_roe}%, size={universe_size}")

            # Call DeepSeek API to generate real universe - AI only, no fallback
            response = self._call_deepseek_api(prompt)
            if response:
                symbols = self._parse_symbols_from_response(response)
                if symbols and len(symbols) >= 10:  # At least 10 symbols
                    logger.info(f"✅ DeepSeek generated {len(symbols)} {screen_type} symbols")
                    return symbols[:universe_size]
                else:
                    logger.warning("DeepSeek response had insufficient symbols")

            # Raise exception instead of using fallback
            raise ValueError(f"AI universe generation failed for {screen_type}: insufficient symbols returned")

        except Exception as e:
            logger.error(f"Failed to generate {screen_type} universe: {e}")
            # Raise exception instead of using fallback
            raise ValueError(f"Failed to generate {screen_type} universe due to API failure: {e}")


    def _call_deepseek_api(self, prompt: str) -> str:
        """Call DeepSeek API to generate universe using centralized service"""
        # Add system message for this specific use case
        full_prompt = """You are a financial analyst expert specializing in stock selection and portfolio construction.

""" + prompt

        response = self.deepseek_service.call_api(full_prompt, max_tokens=1024, temperature=0.1)
        return response or ""

    def _parse_symbols_from_response(self, response: str) -> List[str]:
        """Parse stock symbols from AI response"""
        try:
            # Try to find JSON array in response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                symbols = json.loads(json_match.group())
                # Validate symbols (basic format check)
                valid_symbols = []
                for symbol in symbols:
                    if isinstance(symbol, str) and len(symbol) <= 10 and symbol.isalnum():
                        valid_symbols.append(symbol.upper())
                return valid_symbols[:500]  # Limit to 500 symbols max

            # Fallback: extract symbols from text
            words = response.split()
            symbols = []
            for word in words:
                word = word.strip('",[]() ')
                if len(word) <= 6 and word.isalpha() and word.isupper():
                    symbols.append(word)

            return symbols[:300]  # Limit fallback extraction

        except Exception as e:
            logger.error(f"Failed to parse symbols from AI response: {e}")
            return []




    def generate_universe(self, prompt: str, target_count: int = 30) -> List[str]:
        """
        Generate stock universe using custom prompt

        Args:
            prompt: Custom prompt for AI to generate universe
            target_count: Target number of symbols to generate

        Returns:
            List of stock symbols
        """
        try:
            logger.info(f"🎯 Generating {target_count} symbols using custom prompt")

            # Create full prompt with instructions
            full_prompt = f"""You are an expert financial analyst. {prompt}

CRITICAL REQUIREMENTS:
- Generate EXACTLY {target_count} stock symbols
- Focus on US-listed stocks and ETFs only
- Use current market data (2024-2025)
- Include a mix of individual stocks and relevant ETFs
- Ensure all symbols are valid and actively traded
- Prioritize stocks that meet the specified criteria

RESPONSE FORMAT:
Return ONLY a valid JSON array of ticker symbols (no explanation needed):
["SYMBOL1", "SYMBOL2", "SYMBOL3", ...]

EXAMPLE OUTPUT:
["AAPL", "MSFT", "GOOGL", "QQQ", "SPY"]"""

            # Call AI API
            response = self._call_deepseek_api(full_prompt)
            if not response:
                logger.warning("No response from AI for universe generation")
                return []

            # Extract symbols from response
            symbols = self._parse_symbols_from_response(response)

            if symbols:
                logger.info(f"✅ Generated {len(symbols)} symbols: {symbols[:10]}...")
                return symbols[:target_count]  # Ensure we don't exceed target
            else:
                logger.warning("Failed to parse symbols from AI response")
                return []

        except Exception as e:
            logger.error(f"Error generating universe: {e}")
            return []

    def generate_volatile_universe(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Generate volatile trading stock universe using AI

        Args:
            criteria: User criteria for volatile trading screening

        Returns:
            List of stock symbols for volatile trading screening
        """
        try:
            min_volatility = criteria.get('min_volatility', 30.0)
            min_volume = criteria.get('min_volume', 1000000)
            max_stocks = criteria.get('max_stocks', 60)  # Request 3x for filtering

            prompt = f"""You are an expert swing trader and momentum analyst specializing in high-quality volatile stocks for short-term trading. Generate {max_stocks} stocks using CURRENT 2024-2025 market data.

CRITICAL REQUIREMENTS:
- ONLY actively trading stocks as of 2024-2025
- Price range: $10-$500 (NO penny stocks under $10)
- Market cap: Minimum $500M (NO micro-caps)
- Daily volume: Minimum {min_volume:,.0f} shares
- Listed on NYSE/NASDAQ only

TARGET STOCK PROFILE (Ready-to-Trade Opportunities):
- Stocks that have RECENTLY PULLED BACK 10-30% from recent highs
- Showing signs of BOTTOMING or REVERSING (not still falling)
- Building VOLUME on recent days (accumulation phase)
- NEWS CATALYSTS upcoming (earnings, product launches)
- DIRECTIONAL momentum starting to turn positive
- CONSISTENT volume (not one-day spikes)
- Technical setups: Pullback to support, consolidation after decline
- Institutional participation (smart money accumulating)

PORTFOLIO ALLOCATION (Focus on Pullback Opportunities):

1. MID-CAP TECH AFTER PULLBACK (50%):
   - Software/SaaS that pulled back: DDOG, NET, CRWD, ZS, MDB, PATH
   - Semiconductors after correction: AMD, MRVL, AMAT (if pulled back 15-25%)
   - AI/Cloud after decline: PLTR (if cooled off), SNOW (if corrected)
   - Fintech after selloff: PYPL, AFRM, SOFI (if bottoming)
   Selection criteria:
   * DOWN 15-30% from recent highs
   * Volume starting to increase in last 5 days
   * RSI recovering from oversold (<40 → 45-55)
   * Earnings coming up in next 4 weeks

2. SMALL/MID-CAP RECOVERING (30%):
   - Tech stocks showing reversal: RBLX, U, DASH (if pullback complete)
   - Emerging sectors with support: RDDT, ASAN, OKTA
   * Must show HIGHER LOWS in recent days
   * Volume confirmation on up days
   * Not still in downtrend

3. SECTOR ROTATION OPPORTUNITIES (20%):
   - Biotech after correction: VRTX, REGN, MRNA (if bouncing)
   - Clean Energy if sector rotates: ENPH, FSLR (only if volume returns)
   - Consumer Tech recovery: SHOP (if showing base formation)
   * Sector must show signs of bottoming
   * Relative strength improving
   * News catalyst visible

NO LARGE-CAP unless exceptional setup:
   - Skip: AAPL, MSFT, GOOGL (not volatile enough)
   - Maybe: TSLA, NVDA (ONLY if clear pullback + reversal signal)

STRICT EXCLUSIONS:
❌ Leveraged ETFs (SOXL, TQQQ, SQQQ, SPXL, etc.) - exclude ALL 3x ETFs
❌ Meme stocks (GME, AMC, SAVA) - too risky
❌ Crypto mining stocks (MARA, RIOT, HUT, CLSK) - too volatile/unpredictable
❌ Penny/failing companies: LCID, FSR, FUBO, NIO, XPEV (under $10 or failing)
❌ Bankrupt/Delisted: APE, BBBYQ, FSR
❌ Low-volume stocks (<1M daily average)
❌ Stocks still in STRONG DOWNTREND (making lower lows)
❌ Stocks at or near 52-week highs (wait for pullback)
❌ Stocks with extremely high volatility >100% (too risky like RUN)

PULLBACK QUALITY CHECKS:
✓ Has stock pulled back 15-30% from recent high?
✓ Is there support visible (higher lows forming)?
✓ Is volume increasing on up days vs down days?
✓ Is RSI recovering from oversold territory?
✓ Does price action show accumulation pattern?
✓ Is there institutional ownership >30%?
✓ Does it have upcoming catalyst (earnings, events)?

EXAMPLES OF IDEAL SELECTIONS (Pullback + Recovery):
- Stock down 20% from high, now bouncing off support with volume
- Stock showing RSI recovery from 35 → 50 with volume confirmation
- Stock forming higher lows after selloff, earnings in 2-3 weeks
- Stock with sector rotation into its favor after correction

EXAMPLES OF BAD SELECTIONS (AVOID):
- Stock still making new lows daily (no bottom yet)
- Stock at 52-week high (too extended, wait for pullback)
- Stock with extreme volatility >100% like RUN (too unpredictable)
- Meme stocks, leveraged ETFs, crypto miners

OUTPUT FORMAT:
Return ONLY a JSON array of {max_stocks} ticker symbols:
["PLTR", "AMD", "SNOW", "CRWD", "NET", ...]

Focus on QUALITY volatile stocks that professional traders actually trade.
"""

            response = self.deepseek_service.call_api(prompt, max_tokens=1000)

            if not response:
                logger.error("Empty response from AI for volatile universe generation")
                return []

            # Extract symbols
            symbols = self._parse_symbols_from_response(response)

            if not symbols:
                logger.warning("No symbols extracted from AI response")
                return []

            logger.info(f"✅ AI generated {len(symbols)} volatile trading symbols")
            return symbols[:max_stocks]

        except Exception as e:
            logger.error(f"Error generating volatile universe: {e}")
            return []

def main():
    """Test AI Universe Generator"""
    generator = AIUniverseGenerator()

    # Test dividend universe generation
    print("=== Testing Dividend Universe Generation ===")
    dividend_criteria = {
        'min_dividend_yield': 4.0,
        'max_stocks': 15,
        'focus_sectors': ['Technology', 'Healthcare']
    }
    dividend_universe = generator.generate_dividend_universe(dividend_criteria)
    print(f"Generated {len(dividend_universe)} dividend symbols:")
    print(dividend_universe[:20], "...")

    # Test support level universe generation
    print("\n=== Testing Support Level Universe Generation ===")
    support_criteria = {
        'max_stocks': 10,
        'time_horizon': 'medium'
    }
    support_universe = generator.generate_support_level_universe(support_criteria)
    print(f"Generated {len(support_universe)} support level symbols:")
    print(support_universe[:20], "...")


if __name__ == "__main__":
    main()