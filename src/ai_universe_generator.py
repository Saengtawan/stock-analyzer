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
            criteria: User criteria for dividend screening including:
                - min_dividend_yield: Minimum dividend yield
                - max_stocks: Maximum stocks to return
                - universe_multiplier: Multiplier for universe size (default: 3)

        Returns:
            List of stock symbols for dividend screening
        """
        try:
            min_yield = criteria.get('min_dividend_yield', 3.0)
            max_stocks = criteria.get('max_stocks', 15)
            universe_multiplier = criteria.get('universe_multiplier', 3)  # Default 3x for dividend

            # Calculate universe size based on multiplier
            universe_size = max_stocks * universe_multiplier
            logger.info(f"📊 Generating dividend universe: {universe_size} stocks ({max_stocks} × {universe_multiplier}x multiplier)")

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

    def generate_premarket_universe(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Generate stock universe for pre-market gap scanning

        Args:
            criteria: Scanning criteria including:
                - min_gap_pct: Minimum gap percentage
                - market_caps: List of market cap categories
                - prioritize_tech: Whether to prioritize tech sector
                - max_stocks: Maximum stocks to return

        Returns:
            List of stock symbols likely to have significant gaps
        """
        try:
            min_gap_pct = criteria.get('min_gap_pct', 5.0)
            market_caps = criteria.get('market_caps', ['large', 'mid'])
            prioritize_tech = criteria.get('prioritize_tech', True)
            max_stocks = criteria.get('max_stocks', 20)

            # Adjust universe size to 4x max_stocks for gap scanning
            universe_size = max_stocks * 4

            # Build market cap description
            market_cap_desc = {
                'large': 'Large Cap ($10B+)',
                'mid': 'Mid Cap ($2B-$10B)',
                'small': 'Small Cap ($300M-$2B)'
            }
            market_cap_filter = ' and '.join([market_cap_desc.get(mc, mc) for mc in market_caps])

            # Get current date for context
            from datetime import datetime
            import pytz
            eastern = pytz.timezone('US/Eastern')
            now = datetime.now(eastern)
            current_date = now.strftime('%Y-%m-%d')
            current_month = now.strftime('%B %Y')
            day_of_week = now.strftime('%A')

            prompt = f"""You are an elite pre-market trader and gap trading specialist with real-time market awareness. TODAY IS {current_date} ({day_of_week}). Generate {universe_size} stocks with HIGHEST PROBABILITY of gapping up {min_gap_pct}% or more in pre-market trading.

🎯 CRITICAL SELECTION PRIORITY (Most Important):
1. **IMMEDIATE CATALYSTS** (Next 24-48 hours):
   - Earnings reports scheduled for TODAY or TOMORROW
   - FDA decisions, drug approvals, clinical trial results (this week)
   - Analyst upgrades/downgrades from YESTERDAY or TODAY
   - Major product launches or announcements (within 48 hours)
   - M&A rumors, activist investor activity (breaking news)
   - Unusual options activity (large call purchases yesterday)

2. **RECENT MOMENTUM DRIVERS** (Past 24-72 hours):
   - Stocks that gapped yesterday and continuing uptrend
   - Breaking news overnight (earnings beats, guidance raises)
   - Sector rotation or thematic momentum (AI, quantum, biotech, etc.)
   - Short squeeze candidates with high short interest (>20%)
   - Stocks hitting new 52-week highs with momentum

3. **HISTORICAL GAP PATTERNS**:
   - Stocks known for volatile pre-market moves (ATR >4%)
   - Companies that historically gap on {day_of_week}s
   - Seasonal patterns relevant to {current_month}
   - High beta stocks (β > 1.5) that amplify market moves
   - Stocks with history of gaps >5% in past 30 days

💰 MARKET CAP & SECTOR ALLOCATION:
- Target: {market_cap_filter}
- {'**Technology Sector: 40-50% MINIMUM** (AI, semiconductors, cloud, software)' if prioritize_tech else 'Technology Sector: 20-30%'}
- Healthcare/Biotech: 20-30% (FDA catalysts, trial results)
- Consumer Discretionary: 10-15% (retail earnings, e-commerce)
- Financial: 5-10% (only if major economic data release)
- Energy: 5-10% (only if oil volatility or geopolitical events)
- Small allocation to high-conviction plays in other sectors

🔥 SMART CATALYST DETECTION:
**Earnings Season Focus** ({current_month}):
- Prioritize stocks reporting earnings THIS WEEK
- Companies with history of earnings surprises (>10% beats)
- Stocks with raised guidance in recent quarters
- High analyst estimate revisions (upward trend)

**Sector-Specific Catalysts**:
- Tech: Product launches, AI announcements, chip demand, cloud growth
- Biotech: FDA PDUFA dates, Phase 3 results, pipeline updates
- Retail: Same-store sales, e-commerce growth, holiday guidance
- Finance: Fed decisions, interest rate impacts, loan growth

**Social & Retail Sentiment**:
- Reddit/WallStreetBets momentum stocks (high discussion volume)
- Stocks with unusual options volume (call/put ratio >3)
- Institutional buying pressure (13F filings showing new positions)
- Insider buying clusters (multiple executives buying)

📊 LIQUIDITY & QUALITY REQUIREMENTS:
- Average daily volume: >2M shares (stocks), >500K (ETFs)
- Pre-market volume capability: Must have active pre-market trading
- Float size: Prefer 25-100M shares (sweet spot for volatility)
- Bid-ask spread: <0.3% for large cap, <0.5% for mid cap
- Share price: $15-$500 (avoid low-price volatility)
- Analyst coverage: Minimum 5 analysts (large cap), 3 analysts (mid cap)

⚡ HIGH-PROBABILITY GAP INDICATORS:
- Stocks with earnings whisper numbers beating estimates
- Recent analyst price target raises (>15% upside)
- Sector ETFs showing strong pre-market momentum
- Futures correlation (stocks that move with SPY/QQQ)
- After-hours price action from yesterday (already gapping)
- News flow: Breaking positive news in past 12 hours

🚫 STRICT EXCLUSIONS:
- No penny stocks (price <$10) or delisting warnings
- No stocks with recent fraud/legal issues
- No fresh IPOs (<3 months trading history)
- No stocks that gapped DOWN yesterday (avoid falling knives)
- No extremely illiquid stocks (<500K daily volume)
- No inverse ETFs or leveraged bear ETFs

🎯 OPTIMAL PORTFOLIO MIX:
- 30%: High-confidence earnings plays (reporting today/tomorrow)
- 25%: Momentum continuation (gapped up yesterday, strong follow-through)
- 20%: Catalyst-driven (FDA, product launch, analyst upgrade)
- 15%: Sector rotation plays (money flowing into sector)
- 10%: Short squeeze candidates (high short interest + catalyst)

**FINAL QUALITY CHECK**:
- Prioritize stocks YOU WOULD ACTUALLY TRADE based on gap probability
- Focus on SPECIFIC catalysts happening NOW, not generic characteristics
- Balance between large cap safety and mid cap volatility
- Ensure all symbols are US-listed, actively traded stocks

Select {universe_size} stocks with MAXIMUM gap probability. Think like a professional trader: What's gapping UP TODAY?

Return ONLY a valid JSON array of ticker symbols, no explanations:
["SYMBOL1", "SYMBOL2", "SYMBOL3", ...]"""

            logger.info(f"Generating pre-market gap universe: min_gap={min_gap_pct}%, size={universe_size}")

            # Call DeepSeek API
            response = self._call_deepseek_api(prompt)
            if response:
                symbols = self._parse_symbols_from_response(response)
                if symbols and len(symbols) >= 10:
                    logger.info(f"✅ DeepSeek generated {len(symbols)} pre-market gap symbols")
                    return symbols[:universe_size]
                else:
                    logger.error("DeepSeek response had insufficient symbols")
                    raise ValueError("AI universe generation failed")

            logger.error("DeepSeek API failed for pre-market universe")
            raise ValueError("AI universe generation failed")

        except Exception as e:
            logger.error(f"Failed to generate pre-market universe: {e}")
            raise ValueError(f"AI universe generation failed: {e}")

    def generate_value_universe(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Generate comprehensive stock universe for value/undervalued growth screening

        Args:
            criteria: User criteria for value screening including:
                - max_stocks: Maximum stocks to return
                - screen_type: Type of value screening
                - universe_multiplier: Multiplier for universe size (default: 3)

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
            universe_multiplier = criteria.get('universe_multiplier', 3)  # Default 3x for value

            # Calculate universe size based on multiplier
            universe_size = max_stocks * universe_multiplier
            logger.info(f"📊 Generating value universe: {universe_size} stocks ({max_stocks} × {universe_multiplier}x multiplier)")

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
                seen = set()  # Track seen symbols to avoid duplicates
                for symbol in symbols:
                    if isinstance(symbol, str) and len(symbol) <= 10 and symbol.isalnum():
                        symbol_upper = symbol.upper()
                        if symbol_upper not in seen:  # Only add if not seen before
                            valid_symbols.append(symbol_upper)
                            seen.add(symbol_upper)
                return valid_symbols[:500]  # Limit to 500 symbols max

            # Fallback: extract symbols from text
            words = response.split()
            symbols = []
            seen = set()  # Track seen symbols to avoid duplicates
            for word in words:
                word = word.strip('",[]() ')
                if len(word) <= 6 and word.isalpha() and word.isupper():
                    if word not in seen:  # Only add if not seen before
                        symbols.append(word)
                        seen.add(word)

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

TARGET ENTRY SETUP (Ready-to-Trade Opportunities):
- Stocks that have RECENTLY PULLED BACK 10-30% from recent highs
- Showing signs of BOTTOMING or REVERSING (not still falling)
- Building VOLUME on recent days (accumulation phase)
- NEWS CATALYSTS upcoming (earnings, product launches)
- DIRECTIONAL momentum starting to turn positive
- CONSISTENT volume (not one-day spikes)
- Technical setups: Pullback to support, consolidation after decline
- Institutional participation (smart money accumulating)

PORTFOLIO FOCUS (Pullback + Recovery Opportunities):

1. MID-CAP TECH AFTER PULLBACK (~50%):
   - Software/SaaS that pulled back: DDOG, NET, CRWD, ZS, MDB, PATH, SNOW
   - Semiconductors after correction: AMD, MRVL, AMAT, QCOM, MU
   - AI/Cloud companies: PLTR, SNOW, AI, ORCL
   - Fintech after selloff: PYPL, AFRM, SOFI, SQ, COIN
   Selection criteria:
   * DOWN 15-30% from recent highs
   * Volume increasing in last 5-10 days
   * Recent support holding
   * Earnings catalyst within 4 weeks

2. SMALL/MID-CAP RECOVERING (~30%):
   - Tech showing reversal: RBLX, U, DASH, ASAN, OKTA
   - Emerging sectors: RDDT, HOOD, ABNB, UBER, LYFT
   * Must show higher lows forming
   * Volume confirmation on up days
   * Not in strong downtrend

3. SECTOR ROTATION PLAYS (~20%):
   - Biotech if bouncing: VRTX, REGN, MRNA, BNTX
   - Clean Energy rotation: ENPH, FSLR, RUN
   - Consumer Tech: SHOP, ETSY, W
   * Sector showing strength
   * Relative strength improving
   * Catalyst visible

QUALITY CHECKS FOR PULLBACK ENTRIES:
✓ Stock pulled back 15-30% from recent high?
✓ Support visible (higher lows forming)?
✓ Volume increasing on up days vs down days?
✓ Technical pattern: consolidation, bottoming?
✓ Institutional ownership >30%?
✓ Upcoming catalyst (earnings, events)?

STRICT EXCLUSIONS:
❌ Leveraged ETFs (SOXL, TQQQ, SQQQ, SPXL, UPRO, etc.) - exclude ALL 3x ETFs
❌ Meme stocks (GME, AMC, SAVA) - too unpredictable
❌ Crypto mining (MARA, RIOT, HUT, CLSK) - too volatile
❌ Penny/failing (<$10): LCID, FSR, FUBO, NIO, XPEV
❌ Bankrupt/Delisted companies
❌ Low volume (<{min_volume:,.0f} daily)
❌ Stocks in STRONG DOWNTREND (making lower lows)
❌ Stocks at 52-week highs (wait for pullback)
❌ Extreme volatility >100% (too risky)

EXAMPLES OF IDEAL SELECTIONS:
✓ Stock down 20% from high, bouncing off support with volume
✓ Stock forming higher lows after selloff, earnings in 2-3 weeks
✓ Stock with sector rotation tailwind after correction
✓ Quality company with temporary weakness, strong fundamentals

EXAMPLES TO AVOID:
❌ Stock still making new lows daily (no bottom)
❌ Stock at 52-week high (too extended)
❌ Meme stocks, leveraged ETFs, crypto miners
❌ Stocks with no catalyst or extreme volatility

OUTPUT FORMAT:
Return ONLY a JSON array of {max_stocks} ticker symbols:
["PLTR", "AMD", "SNOW", "CRWD", "NET", "DDOG", ...]

Focus on QUALITY volatile stocks with clear entry setups that professional swing traders actually trade.
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

    def generate_growth_catalyst_universe(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Generate stock universe for 30-day growth catalyst screening

        Args:
            criteria: Screening criteria including:
                - target_gain_pct: Target gain percentage (e.g., 10%)
                - timeframe_days: Timeframe in days (e.g., 30)
                - max_stocks: Maximum stocks to return
                - universe_multiplier: Multiplier for universe size (default: 5 for growth catalyst)

        Returns:
            List of stock symbols with high growth catalyst potential
        """
        try:
            target_gain_pct = criteria.get('target_gain_pct', 10.0)
            timeframe_days = criteria.get('timeframe_days', 30)
            max_stocks = criteria.get('max_stocks', 20)
            universe_multiplier = criteria.get('universe_multiplier', 5)  # Default 5x for growth catalyst

            # Calculate universe size based on multiplier
            universe_size = max_stocks * universe_multiplier
            logger.info(f"📊 Generating growth catalyst universe: {universe_size} stocks ({max_stocks} × {universe_multiplier}x multiplier)")

            prompt = f"""You are an expert growth catalyst analyst specializing in identifying stocks with high-probability {target_gain_pct}%+ gain potential within {timeframe_days} days. Generate {universe_size} stocks using CURRENT 2024-2025 market data.

🎯 MISSION: Find LOW-PRICE stocks with BIG catalysts - VALUE EXPLOSION plays!

CRITICAL SHIFT: We want UNDERVALUED stocks with UPCOMING catalysts!
- LOW PRICE stocks ($10-$100 range) not mega caps
- UNDERVALUED (low P/E, low P/B) not overpriced
- BIG CATALYST coming (FDA, contract, launch) not small news
- HIDDEN GEMS not well-known stocks
- EXPLOSIVE POTENTIAL (+30-100%) not modest gains

Think: Small biotech before FDA approval, Defense stock before contract win
NOT: MSFT, GOOGL, AMZN (already expensive!)

═══════════════════════════════════════════════════════════
📅 FORWARD-LOOKING CATALYSTS (PREDICTIVE)
═══════════════════════════════════════════════════════════

1. UPCOMING EARNINGS CATALYSTS (30% weight):
   ✅ Earnings in next 7-21 days (NOT last week!)
   ✅ Historical earnings beat rate >60%
   ✅ Recent analyst estimate RAISES (last 7 days)
   ✅ Positive pre-earnings drift starting
   ✅ Options unusual call activity building

2. BIG CATALYSTS (35% weight - MOST IMPORTANT!):
   ✅ FDA APPROVAL DATES (biotech with PDUFA dates = EXPLOSIVE!)
   ✅ GOVERNMENT CONTRACTS pending (defense, aerospace)
   ✅ M&A TARGET potential (small companies in hot sectors)
   ✅ MAJOR PRODUCT LAUNCHES (not incremental updates)
   ✅ PATENT APPROVALS / BREAKTHROUGH (game-changing tech)
   ✅ TURNAROUND STORIES (new CEO, restructuring working)
   ✅ EARNINGS RECOVERY (losses → profits transition)

3. SECTOR/MACRO CATALYSTS (20% weight):
   ✅ Gold/Silver prices rising → Mining stocks BEFORE they react
   ✅ Oil prices spiking → Energy stocks BEFORE rally
   ✅ Dollar weakening → Export stocks BEFORE move
   ✅ Fed rate cut expected → Rate-sensitive BEFORE announcement
   ✅ Government contracts → Defense/Aerospace BEFORE award

4. INSIDER/SMART MONEY SIGNALS (15% weight):
   ✅ Recent insider BUYING (last 7-14 days)
   ✅ Unusual options activity (calls > puts)
   ✅ Institutional accumulation (13F filings)
   ✅ Analyst UPGRADES (last 7 days)
   ✅ Short interest declining (covering starting)

   AVOID MEGA CAPS - Focus on VALUE PLAYS:
   ❌ NO: MSFT, GOOGL, AMZN, AAPL, META, NVDA (too expensive!)
   ✅ YES: Small biotech, small defense, small tech with catalysts

   PRIORITY SECTORS FOR EXPLOSIVE MOVES:
   - Biotech: Small caps with FDA catalysts ($500M-$5B)
   - Defense: Mid caps with contract potential
   - Clean Energy: Recovery plays with government support
   - Semiconductor equipment: Undervalued with AI tailwinds
   - SaaS: Small profitable software (not mega caps)

2. NEWS/EVENT CATALYSTS (30% weight):
   ✅ Product launches (Apple events, Tesla deliveries)
   ✅ FDA decisions (biotech approvals)
   ✅ Partnership announcements
   ✅ M&A activity in sector
   ✅ Conference presentations

   HOT SECTORS:
   - AI/ML: Companies announcing AI products
   - Healthcare: FDA calendar, clinical trials
   - EV/Clean Energy: Deliveries, new models
   - Gaming: Game releases, consoles
   - Streaming: Content releases, sub numbers

3. INSIDER/ANALYST CATALYSTS (20% weight):
   ✅ Recent insider buying (last 30 days)
   ✅ Analyst upgrades or PT raises
   ✅ Institutional accumulation
   ✅ Short squeeze potential (>15% SI)
   ✅ Options activity (unusual call volume)

4. TECHNICAL SETUP CATALYSTS (10% weight):
   ✅ Breakout from consolidation
   ✅ Bottoming patterns after pullback
   ✅ Volume surge on recent days
   ✅ Moving average crossovers

═══════════════════════════════════════════════════════════
📊 FUNDAMENTAL QUALITY REQUIREMENTS
═══════════════════════════════════════════════════════════

CRITICAL REQUIREMENTS FOR VALUE EXPLOSIONS:
✓ Market cap: $500M - $20B (Small/Mid caps - explosive potential!)
✓ Price: $10 - $150 (Sweet spot - not too cheap, not too expensive)
✓ P/E ratio: <20 or negative but improving (undervalued!)
✓ Price/Book: <3 (not overvalued)
✓ Analyst coverage: <15 analysts (under-the-radar!)
✓ NOT mega caps (>$100B) - they move slowly!
✓ Daily volume: >$5M (must have some liquidity)

PREFERRED CHARACTERISTICS:
✓ Profitable or path to profitability clear
✓ Strong gross margins (>40%)
✓ Growing market share
✓ Institutional ownership 30-70%
✓ Analyst coverage (at least 5 analysts)

═══════════════════════════════════════════════════════════
🎪 HIGH-CONVICTION CATALYST CATEGORIES
═══════════════════════════════════════════════════════════

A. EARNINGS PLAYS (Week 1-4):
   - Check earnings calendar for next 30 days
   - Focus on companies with:
     * Beat rate >70% historically
     * Rising analyst estimates
     * Strong sector tailwinds
   Examples: Tech giants, cloud leaders, AI plays

B. FDA/REGULATORY EVENTS:
   - Biotech with PDUFA dates
   - Medical device approvals
   - Drug trial results expected
   Examples: Biotech small/mid-caps

C. PRODUCT LAUNCHES:
   - Tech companies with product events
   - Auto companies with delivery numbers
   - Gaming companies with releases
   Examples: AAPL, TSLA, EA, TTWO

D. M&A ACTIVITY:
   - Sectors with active M&A
   - Companies rumored as targets
   - Acquirers with strong balance sheets
   Examples: Healthcare consolidation, fintech

E. MOMENTUM BREAKOUTS:
   - Stocks consolidating near highs
   - Building volume base
   - Sector rotation beneficiaries
   Examples: Sector leaders

═══════════════════════════════════════════════════════════
⚠️ CRITICAL EXCLUSIONS
═══════════════════════════════════════════════════════════

❌ NO stocks without clear catalyst in next 30 days
❌ NO penny stocks (<$5)
❌ NO low-volume stocks (<$5M daily)
❌ NO meme stocks with no fundamentals (GME, AMC)
❌ NO leveraged ETFs (TQQQ, SQQQ, etc.)
❌ NO crypto miners (too volatile)
❌ NO Chinese ADRs (regulatory risk)
❌ NO SPACs pre-merger
❌ NO companies with negative news overhang
❌ NO companies in continuous decline (downtrend last 4+ weeks) unless showing recent reversal

⚡ CRITICAL: PREDICTIVE SIGNALS (not reactive momentum):
✅ Stocks CONSOLIDATING near support BEFORE breakout (not after)
✅ Insider buying in last 7-14 days (smart money positioning)
✅ Unusual options call buying (institutions positioning)
✅ Analyst upgrades in last week (new positive thesis)
✅ Stocks with upcoming catalysts but FLAT price (opportunity!)
✅ Sector leaders BEFORE sector rotation (leading indicators)

❌ EXCLUDE REACTIVE MOMENTUM:
❌ Stocks already up 20%+ in last 2 weeks (too late!)
❌ Stocks at 52-week highs without new catalyst (overextended)
❌ Stocks rallying on old news (momentum chasers)

═══════════════════════════════════════════════════════════
✅ IDEAL SELECTION EXAMPLES
═══════════════════════════════════════════════════════════

PERFECT SETUPS:
✓ NVDA - Earnings in 2 weeks + AI boom + analyst upgrades
✓ TSLA - Delivery numbers next week + new model buzz
✓ SHOP - E-commerce recovery + earnings beat expected
✓ CRWD - Cybersecurity growth + analyst PT raise
✓ AMD - GPU launch + earnings catalyst + insider buying

GOOD SETUPS:
✓ META - Strong ad revenue expected + AI monetization
✓ GOOGL - Cloud growth + AI search features
✓ MSFT - Azure growth + AI copilot momentum
✓ SNOW - Beat and raise pattern + new products
✓ NET - CDN growth + edge computing adoption

═══════════════════════════════════════════════════════════
📋 PORTFOLIO COMPOSITION
═══════════════════════════════════════════════════════════

BALANCE (adjust for market conditions):
- 40%: Large-cap with earnings catalysts
- 30%: Mid-cap with multiple catalysts
- 20%: Small-cap with explosive catalysts
- 10%: Sector rotation/special situations

SECTOR DIVERSIFICATION:
- Technology: 30-40%
- Healthcare: 15-20%
- Consumer: 10-15%
- Financials: 10-15%
- Others: 20-25%

═══════════════════════════════════════════════════════════
🎯 OUTPUT REQUIREMENTS
═══════════════════════════════════════════════════════════

Return ONLY a JSON array of {universe_size} ticker symbols:
["NVDA", "TSLA", "AMD", "MSFT", "GOOGL", "META", ...]

PRIORITIZE stocks with:
1. Clear catalyst in next 2-4 weeks (HIGHEST PRIORITY)
2. Multiple catalysts (earnings + news + analyst)
3. Strong technical setup (momentum building)
4. Institutional interest (not retail hype)
5. Fundamental quality (not pump & dump)

Focus on HIGH-PROBABILITY setups that professional traders actually trade, not lottery tickets.
"""

            # Single round generation - capped at 50-100 stocks to reduce hallucination
            # AI is only a supplement to static universe, not the main source
            ai_cap = min(100, max(50, universe_size))  # Always between 50-100
            logger.info(f"🤖 AI supplement: requesting {ai_cap} stocks (capped to reduce hallucination)")

            # Single API call with moderate token limit
            response = self.deepseek_service.call_api(prompt, max_tokens=2000)

            if not response:
                logger.warning("Empty response from AI")
                return []

            # Extract symbols
            symbols = self._parse_symbols_from_response(response)

            if not symbols:
                logger.warning("No symbols extracted from AI response")
                return []

            # Cap at 100 to reduce hallucination impact
            symbols = symbols[:ai_cap]
            logger.info(f"✅ AI generated {len(symbols)} growth catalyst symbols (capped at {ai_cap})")
            return symbols

        except Exception as e:
            logger.error(f"Error generating growth catalyst universe: {e}")
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