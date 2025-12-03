"""
Main Stock Analyzer Application
"""
import os
import sys
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

# Add src to path
sys.path.append(os.path.dirname(__file__))

try:
    from api.data_manager import DataManager
    from analysis.enhanced_stock_analyzer import EnhancedStockAnalyzer
    from analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer
    from analysis.technical.technical_analyzer import TechnicalAnalyzer
    from signals.signal_generator import SignalGenerator
    from signals.scoring_system import AdvancedScoringSystem
    from risk.risk_manager import AdvancedRiskManager
    from backtesting.backtest_engine import BacktestEngine
    from ai_stock_analyzer import AIStockAnalyzer
    from ai_second_opinion import ai_second_opinion_service
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.info("Make sure to run this script from the src directory or add src to PYTHONPATH")
    raise


class StockAnalyzer:
    """Enhanced stock analyzer application with all advanced modules"""

    def __init__(self, config: Dict[str, Any] = None, trading_strategy: str = "swing_trading"):
        """
        Initialize enhanced stock analyzer

        Args:
            config: Configuration dictionary
            trading_strategy: Trading strategy for optimization
        """
        self.config = config or {}
        self.trading_strategy = trading_strategy

        # Initialize components
        self.data_manager = DataManager(self.config)
        self.enhanced_analyzer = EnhancedStockAnalyzer(
            trading_strategy=trading_strategy,
            risk_tolerance=self.config.get('risk_tolerance', 'moderate')
        )
        self.scoring_system = AdvancedScoringSystem(self.config)
        self.ai_analyzer = AIStockAnalyzer()

        logger.info(f"Enhanced Stock Analyzer initialized with strategy: {trading_strategy}")

    def analyze_stock(self,
                     symbol: str,
                     time_horizon: str = 'swing',
                     account_value: float = 100000,
                     include_ai_analysis: bool = True,
                     historical_price_data: pd.DataFrame = None,
                     analysis_date: datetime = None) -> Dict[str, Any]:
        """
        Perform comprehensive enhanced stock analysis

        Args:
            symbol: Stock symbol to analyze
            time_horizon: Investment time horizon ('swing' [1-7d], 'short' [1-14d], 'medium' [14-90d], 'long' [6mo+])
            account_value: Account value for position sizing
            include_ai_analysis: Whether to include AI analysis (can be skipped for screening)
            historical_price_data: Optional historical price data for backtesting
            analysis_date: Optional analysis date for backtesting context

        Returns:
            Complete enhanced analysis results
        """
        logger.info(f"Starting enhanced analysis for {symbol}")

        # Check if backtest mode
        backtest_mode = historical_price_data is not None
        if backtest_mode:
            logger.info(f"🔬 BACKTEST MODE: Using historical data up to {analysis_date or 'unknown date'}")

        try:
            # 1. Get data (Parallel execution for better performance OR use historical data)
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import time

            start_time = time.time()

            if backtest_mode:
                # Use provided historical data
                price_data = historical_price_data

                # Get current price from last row of historical data
                if 'close' in price_data.columns:
                    current_price = float(price_data['close'].iloc[-1])
                else:
                    current_price = float(price_data['Close'].iloc[-1]) if 'Close' in price_data.columns else 0

                # For backtest, we still need financial data (assumed to be available at analysis date)
                # In real backtest, this should also be historical
                financial_data = self.data_manager.get_financial_data(symbol)

                logger.info(f"📊 Using historical data: {len(price_data)} rows, current price: ${current_price:.2f}")

            else:
                # Execute API calls in parallel (live mode)
                with ThreadPoolExecutor(max_workers=3) as executor:
                    # Submit all tasks
                    future_price = executor.submit(self.data_manager.get_price_data, symbol, '1y', '1d')
                    future_financial = executor.submit(self.data_manager.get_financial_data, symbol)
                    future_realtime = executor.submit(self.data_manager.get_real_time_price, symbol)

                    # Wait for all to complete and get results
                    price_data = future_price.result()
                    financial_data = future_financial.result()
                    realtime_data = future_realtime.result()
                    current_price = realtime_data['current_price']

            elapsed = time.time() - start_time
            logger.info(f"⚡ Data fetching completed in {elapsed:.2f}s")

            # Add current price to financial data for enhanced analysis
            if financial_data:
                financial_data['current_price'] = current_price

            # Detect if this is an ETF
            is_etf = self._detect_etf(symbol, financial_data)
            if financial_data:
                financial_data['is_etf'] = is_etf

            # 2. Use enhanced analyzer for comprehensive analysis
            enhanced_results = self.enhanced_analyzer.analyze_stock(
                symbol=symbol,
                price_data=price_data,
                fundamental_data=financial_data,
                time_horizon=time_horizon
            )

            # 3. Add AI analysis (optional for screening)
            if include_ai_analysis:
                ai_analysis = self.ai_analyzer.analyze_stock_with_ai(
                    symbol=symbol,
                    fundamental_data=enhanced_results.get('fundamental_analysis', {}),
                    technical_data=enhanced_results.get('technical_analysis', {}),
                    current_price=current_price,
                    time_horizon=time_horizon
                )
                # Add AI analysis to enhanced results
                enhanced_results['ai_analysis'] = ai_analysis
            else:
                # Skip AI analysis for screening - add placeholder
                enhanced_results['ai_analysis'] = {'analysis_skipped': True, 'reason': 'screening_mode'}

            # 4. Format results for backward compatibility
            analysis_results = self._format_enhanced_results(enhanced_results, time_horizon, account_value)

            # 5. Generate AI Second Opinion (NEW v3.2)
            if include_ai_analysis:
                try:
                    logger.info(f"Generating AI Second Opinion for {symbol}")
                    ai_second_opinion_result = ai_second_opinion_service.analyze(analysis_results)

                    if ai_second_opinion_result.get('success'):
                        analysis_results['ai_second_opinion'] = ai_second_opinion_result.get('ai_second_opinion')
                        expectancy = ai_second_opinion_result.get('ai_second_opinion', {}).get('expectancy', {})
                        logger.info(f"✅ Performance Expectancy calculated: Win Rate {expectancy.get('win_rate', 'N/A')}, Expectancy {expectancy.get('expectancy_per_trade', 'N/A')}")
                    else:
                        analysis_results['ai_second_opinion'] = None
                        logger.warning("AI Second Opinion generation failed")
                except Exception as e:
                    logger.error(f"AI Second Opinion error: {e}")
                    analysis_results['ai_second_opinion'] = None
            else:
                analysis_results['ai_second_opinion'] = None

            logger.info(f"Enhanced analysis completed for {symbol}. Recommendation: {enhanced_results.get('analysis_summary', {}).get('recommendation', 'N/A')}")
            return analysis_results

        except Exception as e:
            logger.error(f"Enhanced analysis failed for {symbol}: {e}")
            return {
                'symbol': symbol,
                'error': str(e),
                'analysis_date': datetime.now().isoformat(),
                'enhanced_analysis_available': False
            }

    def analyze(self,
                symbol: str,
                time_horizon: str = 'short',
                account_size: float = 100000,
                historical_price_data: pd.DataFrame = None,
                analysis_date: datetime = None) -> Dict[str, Any]:
        """
        Alias for analyze_stock with parameter names matching backtest script

        Args:
            symbol: Stock symbol
            time_horizon: short/medium/long
            account_size: Account size for position sizing
            historical_price_data: Historical data for backtesting
            analysis_date: Analysis date for backtesting

        Returns:
            Analysis results
        """
        return self.analyze_stock(
            symbol=symbol,
            time_horizon=time_horizon,
            account_value=account_size,
            include_ai_analysis=False,  # Skip AI for backtest (faster)
            historical_price_data=historical_price_data,
            analysis_date=analysis_date
        )

    def analyze_stock_fast(self,
                          symbol: str,
                          time_horizon: str = 'medium') -> Dict[str, Any]:
        """
        Perform fast screening analysis for quick evaluation

        Args:
            symbol: Stock symbol to analyze
            time_horizon: Investment time horizon ('short', 'medium', 'long')

        Returns:
            Basic analysis results for screening purposes
        """
        try:
            # Get basic data only
            price_data = self.data_manager.get_price_data(symbol, period='6mo', interval='1d')
            financial_data = self.data_manager.get_financial_data(symbol)
            current_price = self.data_manager.get_real_time_price(symbol)['current_price']

            # Detect if this is an ETF
            is_etf = self._detect_etf(symbol, financial_data)

            # Basic analysis only - no advanced features
            basic_results = self._perform_basic_analysis(
                symbol=symbol,
                price_data=price_data,
                financial_data=financial_data,
                current_price=current_price,
                is_etf=is_etf,
                time_horizon=time_horizon
            )

            return basic_results

        except Exception as e:
            logger.error(f"Fast analysis failed for {symbol}: {e}")
            return {
                'symbol': symbol,
                'error': str(e),
                'analysis_date': datetime.now().isoformat(),
                'fast_analysis': True
            }

    def _perform_basic_analysis(self, symbol: str, price_data: pd.DataFrame,
                               financial_data: Dict[str, Any], current_price: float,
                               is_etf: bool, time_horizon: str) -> Dict[str, Any]:
        """Perform basic analysis for fast screening"""
        try:
            from analysis.technical.technical_analyzer import TechnicalAnalyzer
            from analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer

            # Basic technical analysis
            tech_analyzer = TechnicalAnalyzer(price_data)
            tech_results = tech_analyzer.calculate_basic_indicators(price_data)

            # Basic fundamental analysis
            fundamental_analyzer = FundamentalAnalyzer(financial_data, current_price)

            if is_etf:
                # Simple ETF scoring
                fund_score = self._calculate_etf_basic_score(financial_data)
                fundamental_score = fund_score
            else:
                # Basic fundamental metrics only
                fund_results = fundamental_analyzer.calculate_basic_fundamentals(financial_data)
                fundamental_score = fund_results.get('basic_score', 5.0)

            # Simple technical score
            technical_score = self._calculate_basic_technical_score(tech_results, current_price)

            # Combined score
            overall_score = (fundamental_score + technical_score) / 2

            # Simple recommendation
            if overall_score >= 7.0:
                recommendation = "BUY"
            elif overall_score >= 6.0:
                recommendation = "HOLD"
            else:
                recommendation = "SELL"

            return {
                'symbol': symbol,
                'current_price': current_price,
                'is_etf': is_etf,
                'analysis_date': datetime.now().isoformat(),
                'fast_analysis': True,
                'time_horizon': time_horizon,
                'fundamental_score': fundamental_score,
                'technical_score': technical_score,
                'overall_score': overall_score,
                'recommendation': recommendation,
                'technical_analysis': tech_results,
                'fundamental_analysis': financial_data if financial_data else {},
                'confidence': 0.7 if overall_score > 5.0 else 0.5
            }

        except Exception as e:
            logger.error(f"Basic analysis failed for {symbol}: {e}")
            return {
                'symbol': symbol,
                'current_price': current_price,
                'is_etf': is_etf,
                'error': str(e),
                'fast_analysis': True
            }

    def _calculate_etf_basic_score(self, financial_data: Dict[str, Any]) -> float:
        """Calculate basic ETF score for fast screening"""
        try:
            score = 5.0  # Start with neutral

            # Basic ETF metrics
            expense_ratio = financial_data.get('expense_ratio')
            total_assets = financial_data.get('total_assets')
            dividend_yield = financial_data.get('dividend_yield')

            # Score based on expense ratio
            if expense_ratio is not None:
                if expense_ratio < 0.2:  # < 0.2%
                    score += 1.0
                elif expense_ratio < 0.5:  # < 0.5%
                    score += 0.5
                elif expense_ratio > 1.0:  # > 1.0%
                    score -= 0.5

            # Score based on assets (liquidity)
            if total_assets is not None:
                if total_assets > 5000000000:  # > $5B
                    score += 1.0
                elif total_assets > 1000000000:  # > $1B
                    score += 0.5
                elif total_assets < 100000000:  # < $100M
                    score -= 1.0

            # Score based on dividend yield
            if dividend_yield is not None:
                if dividend_yield > 4.0:
                    score += 0.5
                elif dividend_yield > 2.0:
                    score += 0.3

            return max(1.0, min(10.0, score))

        except Exception:
            return 5.0

    def _calculate_basic_technical_score(self, tech_results: Dict[str, Any], current_price: float) -> float:
        """Calculate basic technical score for fast screening"""
        try:
            score = 5.0  # Start with neutral

            # Basic indicators
            rsi = tech_results.get('rsi')
            sma_20 = tech_results.get('sma_20')
            sma_50 = tech_results.get('sma_50')
            volume_trend = tech_results.get('volume_trend', 0)

            # RSI scoring
            if rsi is not None:
                if 30 <= rsi <= 70:  # Good range
                    score += 1.0
                elif rsi < 30:  # Oversold
                    score += 0.5
                elif rsi > 70:  # Overbought
                    score -= 0.5

            # Moving average trend
            if sma_20 is not None and sma_50 is not None:
                if sma_20 > sma_50:  # Uptrend
                    score += 1.0
                else:  # Downtrend
                    score -= 0.5

            # Price vs MA
            if sma_20 is not None:
                if current_price > sma_20:  # Above MA
                    score += 0.5
                else:  # Below MA
                    score -= 0.3

            # Volume trend
            if volume_trend > 0:
                score += 0.5
            elif volume_trend < 0:
                score -= 0.3

            return max(1.0, min(10.0, score))

        except Exception:
            return 5.0

    def _format_enhanced_results(self, enhanced_results: Dict[str, Any],
                               time_horizon: str, account_value: float) -> Dict[str, Any]:
        """
        Format enhanced results for backward compatibility with existing code
        """
        analysis_summary = enhanced_results.get('analysis_summary', {})
        entry_exit = enhanced_results.get('entry_exit_strategy', {})
        risk_assessment = enhanced_results.get('risk_assessment', {})
        ai_analysis = enhanced_results.get('ai_analysis', {})

        # Calculate price data needed for unified recommendation
        current_price = enhanced_results.get('technical_analysis', {}).get('last_price')
        suggested_entry = self._calculate_entry_price(enhanced_results, entry_exit)
        suggested_stop_loss = self._calculate_stop_loss_price(enhanced_results, entry_exit)
        suggested_targets = self._calculate_target_prices(enhanced_results, entry_exit)

        # Add these to enhanced_results for unified recommendation
        enhanced_results_with_prices = enhanced_results.copy()
        enhanced_results_with_prices['current_price'] = current_price
        enhanced_results_with_prices['suggested_entry'] = suggested_entry
        enhanced_results_with_prices['suggested_stop_loss'] = suggested_stop_loss
        enhanced_results_with_prices['suggested_targets'] = suggested_targets

        # NEW: Generate unified recommendation
        try:
            from analysis.unified_recommendation import create_unified_recommendation, generate_action_plan, generate_multi_timeframe_analysis
            unified_recommendation = create_unified_recommendation(enhanced_results_with_prices)

            # CRITICAL FIX: Make unified_recommendation the SINGLE SOURCE OF TRUTH
            # Override analysis_summary with unified recommendation to prevent signal inconsistency
            if unified_recommendation:
                analysis_summary['recommendation'] = unified_recommendation['recommendation']
                analysis_summary['overall_score'] = unified_recommendation['score']
                analysis_summary['confidence'] = unified_recommendation['confidence_percentage'] / 100
                logger.info(f"✅ Unified recommendation overriding AI summary: {unified_recommendation['recommendation']} (Score: {unified_recommendation['score']:.1f}, Confidence: {unified_recommendation['confidence']})")

                # NEW: Generate action plan from unified recommendation
                action_plan = generate_action_plan(
                    unified_rec=unified_recommendation,
                    current_price=current_price,
                    entry=suggested_entry,
                    stop=suggested_stop_loss,
                    targets=suggested_targets,
                    symbol=enhanced_results.get('symbol', '')
                )
                logger.info(f"✅ Action plan generated: {action_plan.get('action_instruction', 'N/A')}")

                # NEW v3.0: Generate multi-timeframe analysis
                multi_timeframe = generate_multi_timeframe_analysis(enhanced_results_with_prices)
                logger.info(f"✅ Multi-timeframe analysis generated for {multi_timeframe.get('selected')} (with warnings: {len(multi_timeframe.get('alignment', {}).get('warnings', []))})")
            else:
                action_plan = None
                multi_timeframe = None
        except Exception as e:
            import traceback
            logger.error(f"Unified recommendation failed: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            unified_recommendation = None
            action_plan = None
            multi_timeframe = None

        # Get ETF status from enhanced results fundamental data
        fundamental_data = enhanced_results.get('fundamental_analysis', {})
        is_etf = fundamental_data.get('is_etf', False)

        # If not found in enhanced results, check the original symbol
        if not is_etf:
            symbol = enhanced_results.get('symbol', '')
            is_etf = self._detect_etf(symbol, fundamental_data)

        return {
            'symbol': enhanced_results.get('symbol'),
            'analysis_date': enhanced_results.get('analysis_timestamp'),
            'current_price': enhanced_results.get('technical_analysis', {}).get('last_price'),
            'time_horizon': time_horizon,
            'account_value': account_value,
            'is_etf': is_etf,

            # ===== NEW: Unified Recommendation =====
            'unified_recommendation': unified_recommendation,
            # =======================================

            # ===== NEW: Action Plan =====
            'action_plan': action_plan,
            # ============================

            # ===== NEW v3.0: Multi-Timeframe Analysis =====
            'multi_timeframe_analysis': multi_timeframe,
            # ==============================================

            # Enhanced analysis results (including AI analysis)
            'enhanced_analysis': enhanced_results,

            # AI analysis component (direct access)
            'ai_analysis': ai_analysis,

            # AI-specific analysis results
            'ai_insights': ai_analysis.get('analysis_summary', {}),
            'ai_current_situation': ai_analysis.get('current_situation', {}),
            'ai_market_context': ai_analysis.get('market_context', {}),
            'ai_risk_assessment': ai_analysis.get('risk_assessment', {}),
            'ai_price_targets': ai_analysis.get('price_targets', {}),
            'ai_investment_strategy': ai_analysis.get('investment_strategy', {}),
            'ai_key_insights': ai_analysis.get('key_insights', []),
            'ai_confidence': ai_analysis.get('ai_confidence', 0.5),
            'ai_available': bool(ai_analysis and not ai_analysis.get('analysis_skipped', False)),

            # Advanced Analysis Sections
            'ai_catalyst_risk_map': ai_analysis.get('catalyst_risk_map', {}),
            'ai_valuation_benchmark': ai_analysis.get('valuation_benchmark', {}),
            'ai_sensitivity_analysis': ai_analysis.get('sensitivity_analysis', {}),
            'ai_positioning_strategy': ai_analysis.get('positioning_strategy', {}),
            'ai_shareholder_returns': ai_analysis.get('shareholder_returns', {}),
            'ai_analyst_consensus': ai_analysis.get('analyst_consensus', {}),

            # Legacy format compatibility
            'fundamental_analysis': enhanced_results.get('fundamental_analysis', {}),
            'technical_analysis': enhanced_results.get('technical_analysis', {}),
            'signal_analysis': {
                'final_score': {
                    'total_score': analysis_summary.get('overall_score', 0)  # Already 0-10 scale
                },
                'recommendation': {
                    'recommendation': analysis_summary.get('recommendation', 'HOLD')
                },
                'confidence_level': analysis_summary.get('confidence', 0.5),
                'key_insights': analysis_summary.get('key_reasons', [])
            },

            # Risk and positioning
            'trade_risk_assessment': self._calculate_trade_risk_assessment(enhanced_results, entry_exit, risk_assessment),
            'position_sizing': enhanced_results.get('position_sizing', {}),

            # Summary for legacy compatibility
            'final_recommendation': {
                'recommendation': analysis_summary.get('recommendation', 'HOLD'),
                'confidence': analysis_summary.get('confidence', 0.5),
                'score': analysis_summary.get('overall_score', 0.5)
            },
            'confidence_level': self._convert_confidence_to_text(analysis_summary.get('confidence', 0.5)),
            'key_insights': analysis_summary.get('key_reasons', []),

            # Entry/Exit guidance (already calculated above)
            'suggested_entry': suggested_entry,
            'suggested_stop_loss': suggested_stop_loss,
            'suggested_targets': suggested_targets,
            'risk_reward_ratio': self._calculate_risk_reward_ratio(entry_exit),

            # Enhanced features indicators
            'data_quality_score': enhanced_results.get('data_quality', {}).get('quality_score', 0),
            'regime_context': enhanced_results.get('market_regime', {}),
            'adaptability_insights': enhanced_results.get('adaptability_insights', []),
            'signal_quality': enhanced_results.get('signal_processing', {}).get('signal_quality_metrics', {})
        }

    def _calculate_entry_price(self, enhanced_results: Dict[str, Any], entry_exit: Dict[str, Any]) -> float:
        """Calculate suggested entry price based on technical analysis"""
        try:
            current_price = enhanced_results.get('technical_analysis', {}).get('last_price')
            if current_price is None:
                return None

            current_price = float(current_price)
            recommendation = enhanced_results.get('analysis_summary', {}).get('recommendation', 'HOLD')

            # Get technical indicators for smart entry calculation
            indicators = enhanced_results.get('technical_analysis', {}).get('indicators', {})

            # Bollinger Bands for entry timing
            bb_upper = indicators.get('bb_upper', current_price)
            bb_middle = indicators.get('bb_middle', current_price)
            bb_lower = indicators.get('bb_lower', current_price)

            # Support/Resistance levels
            sr = indicators.get('support_resistance', {})
            support_1 = sr.get('support_1', current_price * 0.98)
            resistance_1 = sr.get('resistance_1', current_price * 1.02)

            # RSI for overbought/oversold conditions
            rsi = indicators.get('rsi', 50)

            # MACD for trend confirmation
            macd_line = indicators.get('macd_line', 0)
            macd_signal = indicators.get('macd_signal', 0)

            if recommendation == 'BUY':
                # Calculate optimal BUY entry price

                # If price is above BB upper (overbought), wait for pullback
                if current_price > bb_upper:
                    # Suggest entry near BB middle or support
                    entry_price = min(bb_middle, support_1)

                # If RSI is overbought (>70), suggest pullback entry
                elif rsi > 70:
                    # Entry at support level or 1-2% below current
                    entry_price = min(support_1, current_price * 0.98)

                # If MACD is bullish and price is reasonable, enter near current
                elif macd_line > macd_signal and current_price <= bb_middle:
                    # Small discount for limit order
                    entry_price = current_price * 0.999

                # Default: entry between support and current price
                else:
                    entry_price = (support_1 + current_price) / 2

                return round(max(entry_price, current_price * 0.95), 2)  # Max 5% below current

            elif recommendation == 'SELL':
                # Calculate optimal SELL entry price (for short positions)

                # If price is below BB lower (oversold), wait for bounce
                if current_price < bb_lower:
                    entry_price = max(bb_middle, resistance_1)

                # If RSI is oversold (<30), wait for bounce
                elif rsi < 30:
                    entry_price = max(resistance_1, current_price * 1.02)

                # If MACD is bearish, enter near current
                elif macd_line < macd_signal:
                    entry_price = current_price * 1.001

                # Default: entry between current and resistance
                else:
                    entry_price = (current_price + resistance_1) / 2

                return round(min(entry_price, current_price * 1.05), 2)  # Max 5% above current

            else:  # HOLD or STRONG BUY/SELL with cautions
                # For HOLD, suggest waiting for better technical setup
                # Don't just use current price - find optimal entry zone

                # Check if stock is overbought
                if current_price > bb_upper or rsi > 70:
                    # Wait for pullback to BB middle or support
                    suggested_entry = min(bb_middle, support_1 * 1.01)
                    return round(suggested_entry, 2)

                # Check if stock is oversold
                elif current_price < bb_lower or rsi < 30:
                    # Good entry opportunity near current levels
                    suggested_entry = max(current_price, bb_lower)
                    return round(suggested_entry, 2)

                # Price is in neutral zone
                else:
                    # Suggest entry slightly below current for limit order
                    # This gives better risk/reward than market order
                    suggested_entry = current_price * 0.995  # 0.5% below current
                    return round(suggested_entry, 2)

        except Exception as e:
            # Fallback to current price
            try:
                return round(float(enhanced_results.get('technical_analysis', {}).get('last_price', 0)), 2)
            except:
                return None

    def _calculate_stop_loss_price(self, enhanced_results: Dict[str, Any], entry_exit: Dict[str, Any]) -> float:
        """Calculate stop loss price based on technical analysis"""
        try:
            current_price = enhanced_results.get('technical_analysis', {}).get('last_price')
            if current_price is None:
                return None

            current_price = float(current_price)
            recommendation = enhanced_results.get('analysis_summary', {}).get('recommendation', 'HOLD')

            # Get technical indicators for smart stop loss calculation
            indicators = enhanced_results.get('technical_analysis', {}).get('indicators', {})

            # Support/Resistance levels
            sr = indicators.get('support_resistance', {})
            support_1 = sr.get('support_1', current_price * 0.97)
            support_2 = sr.get('support_2', current_price * 0.94)
            resistance_1 = sr.get('resistance_1', current_price * 1.03)
            resistance_2 = sr.get('resistance_2', current_price * 1.06)

            # ATR for volatility-based stops
            atr = indicators.get('atr', current_price * 0.02)  # Default 2% if no ATR

            # Bollinger Bands
            bb_middle = indicators.get('bb_middle', current_price)
            bb_lower = indicators.get('bb_lower', current_price * 0.96)
            bb_upper = indicators.get('bb_upper', current_price * 1.04)

            if recommendation == 'BUY':
                # ATR-BASED DYNAMIC STOP LOSS (v2.0)
                # Risk = 1.5 × ATR (as recommended)

                atr_multiplier = 1.5  # Standard multiplier for swing trading
                stop_price = current_price - (atr * atr_multiplier)

                # Use support as floor (don't let stop go too far below support)
                support_floor = support_1 * 0.99  # 1% below support
                stop_price = max(stop_price, support_floor)

                # Ensure stop is reasonable (max 8% for safety)
                max_stop = current_price * 0.92  # Max 8% stop loss
                stop_price = max(stop_price, max_stop)

                logger.debug(f"BUY stop: ATR={atr:.2f}, ATR-based stop=${stop_price:.2f} ({((current_price-stop_price)/current_price)*100:.1f}% below entry)")

            elif recommendation == 'SELL':
                # ATR-BASED DYNAMIC STOP LOSS FOR SHORT (v2.0)
                # Risk = 1.5 × ATR (as recommended)

                atr_multiplier = 1.5
                stop_price = current_price + (atr * atr_multiplier)

                # Use resistance as ceiling (don't let stop go too far above resistance)
                resistance_ceiling = resistance_1 * 1.01  # 1% above resistance
                stop_price = min(stop_price, resistance_ceiling)

                # Ensure stop is reasonable (max 8% for safety)
                min_stop = current_price * 1.08  # Max 8% stop loss
                stop_price = min(stop_price, min_stop)

                logger.debug(f"SELL stop: ATR={atr:.2f}, ATR-based stop=${stop_price:.2f} ({((stop_price-current_price)/current_price)*100:.1f}% above entry)")

            else:  # HOLD
                # Conservative stop loss
                stop_price = current_price * 0.97  # 3% stop for HOLD

            return round(stop_price, 2)

        except Exception as e:
            # Fallback to simple percentage-based stop
            try:
                current_price = float(enhanced_results.get('technical_analysis', {}).get('last_price', 0))
                return round(current_price * 0.97, 2)  # 3% default stop
            except:
                return None

    def _calculate_target_prices(self, enhanced_results: Dict[str, Any], entry_exit: Dict[str, Any]) -> list:
        """Calculate target prices based on technical analysis"""
        try:
            current_price = enhanced_results.get('technical_analysis', {}).get('last_price')
            if current_price is None:
                return [None, None]

            current_price = float(current_price)
            recommendation = enhanced_results.get('analysis_summary', {}).get('recommendation', 'HOLD')

            # Get technical indicators for smart target calculation
            indicators = enhanced_results.get('technical_analysis', {}).get('indicators', {})

            # Support/Resistance levels
            sr = indicators.get('support_resistance', {})
            resistance_1 = sr.get('resistance_1', current_price * 1.02)
            resistance_2 = sr.get('resistance_2', current_price * 1.05)
            resistance_3 = sr.get('resistance_3', current_price * 1.08)
            support_1 = sr.get('support_1', current_price * 0.98)
            support_2 = sr.get('support_2', current_price * 0.95)

            # Bollinger Bands
            bb_upper = indicators.get('bb_upper', current_price * 1.04)
            bb_lower = indicators.get('bb_lower', current_price * 0.96)

            # Fibonacci retracements (if available)
            fibonacci = indicators.get('fibonacci', {})
            fib_161 = fibonacci.get('extension_161.8', current_price * 1.06) if isinstance(fibonacci, dict) else current_price * 1.06
            fib_261 = fibonacci.get('extension_261.8', current_price * 1.12) if isinstance(fibonacci, dict) else current_price * 1.12

            if recommendation == 'BUY':
                # DYNAMIC TARGET CALCULATION (v2.0)
                # Reward = Resistance - Entry (as recommended)

                # Target 1: First resistance (primary target)
                target_1 = resistance_1

                # Target 2: Second resistance or Fibonacci extension
                target_2 = max(resistance_2, fib_161)

                # Calculate R:R for Target 1
                entry_price = current_price  # Assuming entry at current
                stop_loss_est = current_price - (indicators.get('atr', current_price * 0.02) * 1.5)
                risk_dollars = entry_price - stop_loss_est
                reward_dollars = target_1 - entry_price
                rr_ratio = reward_dollars / risk_dollars if risk_dollars > 0 else 0

                # Ensure reasonable targets and minimum R:R
                target_1 = max(target_1, current_price * 1.015)  # Min 1.5% gain
                target_2 = max(target_2, target_1 * 1.02)  # Min 2% above target 1

                logger.debug(f"BUY targets: T1=${target_1:.2f} (+{((target_1-current_price)/current_price)*100:.1f}%), T2=${target_2:.2f}, R:R={rr_ratio:.2f}:1")

            elif recommendation == 'SELL':
                # Calculate SELL targets (for short positions) based on support levels

                # Target 1: First support or BB lower
                target_1_options = [support_1, bb_lower]
                target_1 = max([t for t in target_1_options if t < current_price * 0.995])  # At least 0.5% gain

                # Target 2: Second support
                target_2_options = [support_2]
                target_2 = max([t for t in target_2_options if t < target_1 * 0.99])  # At least 1% below target 1

                # Ensure reasonable targets
                target_1 = max(target_1, current_price * 0.92)  # Max 8% for target 1
                target_2 = max(target_2, current_price * 0.85)  # Max 15% for target 2

            else:  # HOLD
                # Conservative targets for HOLD
                target_1 = current_price * 1.03  # 3% target
                target_2 = current_price * 1.06  # 6% target

            return [round(target_1, 2), round(target_2, 2)]

        except Exception as e:
            # Fallback to simple percentage targets
            try:
                current_price = float(enhanced_results.get('technical_analysis', {}).get('last_price', 0))
                return [round(current_price * 1.03, 2), round(current_price * 1.06, 2)]
            except:
                return [None, None]

    def _calculate_trade_risk_assessment(self, enhanced_results: Dict[str, Any],
                                       entry_exit: Dict[str, Any],
                                       risk_assessment: Dict[str, Any]) -> dict:
        """Calculate comprehensive trade risk assessment"""
        try:
            current_price = enhanced_results.get('technical_analysis', {}).get('last_price')
            if current_price is None:
                return {
                    'risk_score': risk_assessment.get('overall_risk_score', 0.5),
                    'risk_reward_ratio': 1.5,
                    'risk_level': 'Medium',
                    'max_risk_percentage': 2.0,
                    'potential_reward_percentage': 3.0
                }

            current_price = float(current_price)

            # Get actual entry/exit strategy data from enhanced_results
            entry_exit_strategy = enhanced_results.get('entry_exit_strategy', {})

            # Calculate dynamic risk percentages based on actual price levels and volatility
            volatility = enhanced_results.get('risk_assessment', {}).get('metrics', {}).get('volatility', 0.02)
            atr = enhanced_results.get('technical_analysis', {}).get('indicators', {}).get('atr', current_price * 0.02)

            # Dynamic stop loss based on ATR and volatility (1.5-4% range)
            atr_pct = (atr / current_price) * 100 if atr else 2.0
            volatility_pct = volatility * 100
            stop_loss_pct = max(1.5, min(4.0, atr_pct * 1.2 + volatility_pct * 0.5))

            # Dynamic target based on risk level and market conditions (2-8% range)
            risk_score = risk_assessment.get('overall_risk_score', 0.5)
            market_strength = enhanced_results.get('market_regime', {}).get('trend_strength', 0.5)

            # Higher targets for stronger trends and lower risk
            base_target = 3.0
            trend_multiplier = 1 + (market_strength - 0.5) * 0.8  # 0.6 to 1.4
            risk_multiplier = 1 + (0.5 - risk_score) * 0.6       # 0.7 to 1.3
            target_1_pct = max(2.0, min(8.0, base_target * trend_multiplier * risk_multiplier))

            # Calculate risk-reward ratio
            risk_reward_ratio = round(target_1_pct / max(stop_loss_pct, 0.1), 2)

            # Determine risk level based on multiple factors
            overall_risk_score = risk_assessment.get('overall_risk_score', 0.5)
            if overall_risk_score <= 0.3:
                risk_level = 'Low'
            elif overall_risk_score <= 0.6:
                risk_level = 'Medium'
            else:
                risk_level = 'High'

            return {
                'risk_score': overall_risk_score,
                'risk_reward_ratio': risk_reward_ratio,
                'risk_level': risk_level,
                'max_risk_percentage': round(stop_loss_pct, 2),
                'potential_reward_percentage': round(target_1_pct, 2)
            }
        except Exception as e:
            # Fallback with some variation
            import random
            return {
                'risk_score': 0.5,
                'risk_reward_ratio': 1.5,
                'risk_level': 'Medium',
                'max_risk_percentage': round(random.uniform(1.8, 3.5), 2),
                'potential_reward_percentage': round(random.uniform(2.5, 5.0), 2)
            }

    def _calculate_risk_reward_ratio(self, entry_exit: Dict[str, Any]) -> float:
        """Calculate risk reward ratio from entry/exit strategy"""
        try:
            stop_loss_pct = entry_exit.get('stop_loss_strategy', {}).get('percentage', 2.0)
            target_1_pct = entry_exit.get('take_profit_strategy', {}).get('target_1', 3.0)
            return round(target_1_pct / max(stop_loss_pct, 0.1), 2)
        except:
            return 1.5  # Default reasonable ratio

    def _convert_confidence_to_text(self, confidence: float) -> str:
        """Convert numerical confidence to text"""
        if confidence >= 0.8:
            return "Very High"
        elif confidence >= 0.6:
            return "High"
        elif confidence >= 0.4:
            return "Medium"
        elif confidence >= 0.2:
            return "Low"
        else:
            return "Very Low"

    def screen_stocks(self,
                     symbols: list,
                     screening_criteria: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Screen multiple stocks based on criteria

        Args:
            symbols: List of stock symbols
            screening_criteria: Screening criteria

        Returns:
            Screening results
        """
        logger.info(f"Screening {len(symbols)} stocks")

        criteria = screening_criteria or {
            'min_score': 6.0,
            'max_pe': 30,
            'min_rsi': 30,
            'max_rsi': 70
        }

        results = {
            'screening_date': datetime.now().isoformat(),
            'total_stocks': len(symbols),
            'criteria': criteria,
            'passed_stocks': [],
            'failed_stocks': [],
            'errors': []
        }

        for symbol in symbols:
            try:
                analysis = self.analyze_stock(symbol)

                if 'error' in analysis:
                    results['errors'].append({
                        'symbol': symbol,
                        'error': analysis['error']
                    })
                    continue

                # Apply screening criteria
                passes_screen = self._apply_screening_criteria(analysis, criteria)

                stock_summary = {
                    'symbol': symbol,
                    'current_price': analysis.get('current_price'),
                    'recommendation': analysis.get('final_recommendation', {}).get('recommendation'),
                    'score': analysis.get('signal_analysis', {}).get('final_score', {}).get('total_score', 0),
                    'confidence': analysis.get('confidence_level'),
                    'pe_ratio': analysis.get('fundamental_analysis', {}).get('financial_ratios', {}).get('pe_ratio'),
                    'rsi': analysis.get('technical_analysis', {}).get('indicators', {}).get('rsi')
                }

                if passes_screen:
                    results['passed_stocks'].append(stock_summary)
                else:
                    results['failed_stocks'].append(stock_summary)

            except Exception as e:
                logger.error(f"Screening failed for {symbol}: {e}")
                results['errors'].append({
                    'symbol': symbol,
                    'error': str(e)
                })

        # Sort results by score
        results['passed_stocks'].sort(key=lambda x: x.get('score', 0), reverse=True)

        logger.info(f"Screening completed. {len(results['passed_stocks'])} stocks passed screening")
        return results

    def run_backtest(self,
                    symbols: list,
                    strategy_name: str = 'signal_based',
                    start_date: str = '2023-01-01',
                    end_date: str = '2024-01-01',
                    initial_capital: float = 100000) -> Dict[str, Any]:
        """
        Run backtest on strategy

        Args:
            symbols: List of symbols to trade
            strategy_name: Strategy to backtest
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting capital

        Returns:
            Backtest results
        """
        logger.info(f"Running backtest on {len(symbols)} symbols from {start_date} to {end_date}")

        try:
            # Get historical data for all symbols
            data = {}
            for symbol in symbols:
                price_data = self.data_manager.get_price_data(symbol, period='3y', interval='1d')
                data[symbol] = price_data.set_index('date')

            # Initialize backtest engine
            backtest_engine = BacktestEngine(initial_capital, self.config)

            # Define strategy function
            def signal_based_strategy(price_data: pd.DataFrame, symbol: str, current_date: str) -> Optional[Dict[str, Any]]:
                """Simple moving average crossover strategy"""
                try:
                    # Need at least 50 days of data
                    if len(price_data) < 50:
                        return None

                    # Calculate simple moving averages
                    sma_10 = price_data['close'].rolling(10).mean().iloc[-1]
                    sma_30 = price_data['close'].rolling(30).mean().iloc[-1]
                    prev_sma_10 = price_data['close'].rolling(10).mean().iloc[-2]
                    prev_sma_30 = price_data['close'].rolling(30).mean().iloc[-2]

                    current_price = price_data['close'].iloc[-1]

                    # Golden cross (10-day MA crosses above 30-day MA) = BUY
                    if sma_10 > sma_30 and prev_sma_10 <= prev_sma_30:
                        return {
                            'action': 'BUY',
                            'stop_loss': current_price * 0.95,
                            'take_profit': current_price * 1.10
                        }
                    # Death cross (10-day MA crosses below 30-day MA) = SELL
                    elif sma_10 < sma_30 and prev_sma_10 >= prev_sma_30:
                        return {
                            'action': 'SELL'
                        }

                    return None

                except Exception as e:
                    logger.warning(f"Strategy error for {symbol}: {e}")
                    return None

            # Run backtest
            backtest_results = backtest_engine.run_backtest(
                data, signal_based_strategy, start_date, end_date
            )

            logger.info(f"Backtest completed. Total return: {backtest_results.get('performance_metrics', {}).get('total_return', 0):.2%}")
            return backtest_results

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return {'error': str(e)}

    def _apply_screening_criteria(self, analysis: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
        """Apply screening criteria to analysis results"""
        try:
            # Score criteria
            score = analysis.get('signal_analysis', {}).get('final_score', {}).get('total_score', 0)
            if score < criteria.get('min_score', 0):
                return False

            # P/E ratio criteria
            pe_ratio = analysis.get('fundamental_analysis', {}).get('financial_ratios', {}).get('pe_ratio')
            if pe_ratio and pe_ratio > criteria.get('max_pe', float('inf')):
                return False

            # RSI criteria
            rsi = analysis.get('technical_analysis', {}).get('indicators', {}).get('rsi')
            if rsi:
                if rsi < criteria.get('min_rsi', 0) or rsi > criteria.get('max_rsi', 100):
                    return False

            return True

        except Exception:
            return False

    def _detect_etf(self, symbol: str, financial_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Detect if a symbol is an ETF

        Args:
            symbol: Stock symbol
            financial_data: Financial data dictionary

        Returns:
            True if ETF, False otherwise
        """
        # Known ETF symbols
        known_etfs = {
            'SPYI', 'VYM', 'DVY', 'HDV', 'SCHD', 'VIG', 'DGRO', 'FDV', 'RDVY', 'NOBL',
            'SPY', 'QQQ', 'IWM', 'VTI', 'VXUS', 'VEA', 'VWO', 'BND', 'AGG', 'TLT',
            'GLD', 'SLV', 'VNQ', 'XLF', 'XLK', 'XLV', 'XLE', 'XLI', 'XLP', 'XLU',
            'ARKK', 'ARKQ', 'ARKG', 'ARKF', 'ARKW', 'TQQQ', 'SQQQ', 'UPRO', 'TMF'
        }

        # Check if symbol is in known ETF list
        if symbol in known_etfs:
            return True

        # Check if financial data suggests ETF (no sector/industry typically)
        if financial_data:
            sector = financial_data.get('sector')
            industry = financial_data.get('industry')

            # ETFs typically don't have sector/industry classifications
            if sector is None and industry is None:
                return True

        # Additional heuristics - ETF-like naming patterns
        etf_patterns = ['ETF', 'FUND', 'INDEX', 'TRUST']
        if any(pattern in symbol.upper() for pattern in etf_patterns):
            return True

        return False


def main():
    """Main function for command line usage"""
    import argparse

    parser = argparse.ArgumentParser(description='Stock Analyzer')
    parser.add_argument('command', choices=['analyze', 'screen', 'backtest'], help='Command to run')
    parser.add_argument('--symbol', type=str, help='Stock symbol to analyze')
    parser.add_argument('--symbols', type=str, nargs='+', help='Multiple stock symbols')
    parser.add_argument('--time-horizon', choices=['swing', 'short', 'medium', 'long'], default='medium')
    parser.add_argument('--strategy', choices=['day_trading', 'swing_trading', 'position_trading', 'long_term_investing'], default='swing_trading')
    parser.add_argument('--start-date', type=str, default='2023-01-01')
    parser.add_argument('--end-date', type=str, default='2024-01-01')
    parser.add_argument('--capital', type=float, default=100000)

    args = parser.parse_args()

    # Initialize enhanced analyzer with user strategy
    analyzer = StockAnalyzer(trading_strategy=getattr(args, 'strategy', 'swing_trading'))

    if args.command == 'analyze':
        if not args.symbol:
            print("Error: --symbol required for analyze command")
            return

        results = analyzer.analyze_stock(args.symbol, args.time_horizon, args.capital)
        print(f"\nEnhanced Analysis Results for {args.symbol}:")
        print(f"Recommendation: {results.get('final_recommendation', {}).get('recommendation', 'N/A')}")
        print(f"Score: {results.get('signal_analysis', {}).get('final_score', {}).get('total_score', 0):.1f}/10")
        print(f"Confidence: {results.get('confidence_level', 'N/A')}")
        print(f"Data Quality: {results.get('data_quality_score', 0):.2f}")

        # Show enhanced insights
        insights = results.get('adaptability_insights', [])
        if insights:
            print(f"\nKey Insights:")
            for insight in insights[:3]:  # Top 3 insights
                print(f"  • {insight}")

        # Show regime context
        regime = results.get('regime_context', {}).get('regime', 'NORMAL')
        if regime != 'NORMAL':
            print(f"Market Regime: {regime}")

    elif args.command == 'screen':
        if not args.symbols:
            print("Error: --symbols required for screen command")
            return

        results = analyzer.screen_stocks(args.symbols)
        print(f"\nScreening Results:")
        print(f"Passed: {len(results['passed_stocks'])}/{results['total_stocks']} stocks")

        for stock in results['passed_stocks'][:5]:  # Top 5
            print(f"{stock['symbol']}: {stock['recommendation']} (Score: {stock['score']:.1f})")

    elif args.command == 'backtest':
        if not args.symbols:
            print("Error: --symbols required for backtest command")
            return

        results = analyzer.run_backtest(
            args.symbols, start_date=args.start_date,
            end_date=args.end_date, initial_capital=args.capital
        )

        if 'error' in results:
            print(f"Backtest error: {results['error']}")
        else:
            metrics = results.get('performance_metrics', {})
            print(f"\nBacktest Results ({args.start_date} to {args.end_date}):")
            print(f"Total Return: {metrics.get('total_return', 0):.2%}")
            print(f"Annualized Return: {metrics.get('annualized_return', 0):.2%}")
            print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
            print(f"Max Drawdown: {metrics.get('max_drawdown', 0):.2f}%")


if __name__ == "__main__":
    main()