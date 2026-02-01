"""
Flask Web Application for Stock Analyzer
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
import json
import sys
import os
from datetime import datetime
from loguru import logger

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from main import StockAnalyzer
from utils import clean_analysis_results, make_json_serializable
from symbol_utils import SymbolUtils
from screeners.support_level_screener import SupportLevelScreener
from screeners.dividend_screener import DividendGrowthScreener
from screeners.value_screener import ValueStockScreener
from screeners.premarket_scanner import PremarketScanner
from screeners.growth_catalyst_screener import GrowthCatalystScreener
from screeners.momentum_growth_screener import MomentumGrowthScreener
from screeners.pullback_catalyst_screener import PullbackCatalystScreener
from ai_market_analyst import AIMarketAnalyst
from analysis.fundamental.earnings_analyst import EarningsAnalystAnalyzer
from analysis.enhanced_features import analyze_stock as enhanced_analyze


app = Flask(__name__)
CORS(app)

# Initialize stock analyzer and screeners (now AI-only)
analyzer = StockAnalyzer()
support_screener = SupportLevelScreener(analyzer)
dividend_screener = DividendGrowthScreener(analyzer)
value_screener = ValueStockScreener(analyzer)
premarket_scanner = PremarketScanner(analyzer.data_manager.yahoo_client)
growth_catalyst_screener = GrowthCatalystScreener(analyzer)
momentum_growth_screener = MomentumGrowthScreener(analyzer)
pullback_catalyst_screener = PullbackCatalystScreener(analyzer)
market_analyst = AIMarketAnalyst()


def enrich_with_etf_info(results):
    """Add ETF information to screening results"""
    if isinstance(results, list):
        for item in results:
            if 'symbol' in item:
                etf_info = SymbolUtils.get_etf_info(item['symbol'])
                if etf_info:
                    item['etf_info'] = etf_info
    elif isinstance(results, dict) and 'symbol' in results:
        etf_info = SymbolUtils.get_etf_info(results['symbol'])
        if etf_info:
            results['etf_info'] = etf_info
    return results

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/analyze')
def analyze_page():
    """Stock analysis page"""
    return render_template('analyze.html')

@app.route('/screen')
def screen_page():
    """Stock screening page"""
    return render_template('screen.html')

@app.route('/news')
def news_page():
    """News and market analysis page"""
    return render_template('news.html')

@app.route('/backtest')
def backtest_page():
    """Backtesting page"""
    return render_template('backtest.html')

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """API endpoint for stock analysis"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        time_horizon = data.get('time_horizon', 'medium')
        account_value = data.get('account_value', 100000)

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        # Perform analysis
        results = analyzer.analyze_stock(symbol, time_horizon, account_value)

        # DEBUG: Log unified_recommendation structure
        unified_rec = results.get('unified_recommendation', {})
        weights = unified_rec.get('weights_applied', {})
        logger.info(f"🔍 API DEBUG - unified_recommendation exists: {bool(unified_rec)}")
        logger.info(f"🔍 API DEBUG - weights_applied exists: {bool(weights)}")
        logger.info(f"🔍 API DEBUG - weights_applied content: {weights}")

        # Add ETF information
        etf_info = SymbolUtils.get_etf_info(symbol)
        if etf_info:
            results['etf_info'] = etf_info

        # === Enhanced Features ===
        try:
            # Extract data for enhanced analysis
            tech = results.get('technical_analysis', {})
            fund = results.get('fundamental_analysis', {})
            unified = results.get('unified_recommendation', {})

            # Get current price - try multiple sources
            # Debug: Check each source
            last_price = tech.get('last_price')
            tech_current = tech.get('current_price')
            unified_current = unified.get('current_price')
            unified_entry = unified.get('entry_point')

            logger.info(f"Price sources - last_price: {last_price}, tech_current: {tech_current}, unified_current: {unified_current}, unified_entry: {unified_entry}")

            current_price = (
                last_price or
                tech_current or
                unified_current or
                unified_entry or
                0
            )

            # Skip if current_price is 0
            if current_price == 0:
                logger.warning(f"Enhanced features skipped: current_price is 0. Tech keys: {list(tech.keys())[:10]}, Unified keys: {list(unified.keys())[:10]}")
                results['enhanced_features'] = None
            else:
                # Get technical indicators
                rsi = tech.get('rsi', 50)
                volume_ratio = tech.get('volume_vs_avg', 1.0) if tech.get('volume_vs_avg', 0) != 0 else 1.0

                # Get support/resistance
                support = tech.get('support_1', current_price * 0.95)
                resistance = tech.get('resistance_1', current_price * 1.05)

                # Ensure support and resistance are not 0
                if support == 0:
                    support = current_price * 0.95
                if resistance == 0:
                    resistance = current_price * 1.05

                # Get targets from recommendation
                entry_zone_low = support
                entry_zone_high = unified.get('entry_point', current_price * 0.98) if unified.get('entry_point') else current_price * 0.98
                tp1 = unified.get('target_price', resistance) if unified.get('target_price') else resistance
                tp2 = tp1 * 1.05 if tp1 != 0 else current_price * 1.1
                stop_loss = unified.get('stop_loss', support * 0.98) if unified.get('stop_loss') else support * 0.98

                # Ensure tp1, tp2, stop_loss are not 0
                if tp1 == 0:
                    tp1 = current_price * 1.05
                if tp2 == 0:
                    tp2 = current_price * 1.1
                if stop_loss == 0:
                    stop_loss = current_price * 0.95

                # Market regime - extract string from dict if needed
                market_regime_data = tech.get('market_regime', 'sideways')
                if isinstance(market_regime_data, dict):
                    # Extract regime name from nested structure
                    current_regime = market_regime_data.get('current', {})
                    regime_name = current_regime.get('current_regime', 'sideways')
                    # Convert enum to string if needed
                    market_regime = str(regime_name).split('.')[-1].lower() if hasattr(regime_name, 'name') else str(regime_name)
                elif isinstance(market_regime_data, str):
                    market_regime = market_regime_data
                else:
                    market_regime = 'sideways'

                logger.info(f"Enhanced features params: price={current_price}, support={support}, resistance={resistance}, tp1={tp1}, tp2={tp2}, sl={stop_loss}")

                # Run enhanced analysis
                enhanced_results = enhanced_analyze(
                    symbol=symbol,
                    current_price=current_price,
                    entry_zone=(entry_zone_low, entry_zone_high),
                    support=support,
                    resistance=resistance,
                    tp1=tp1,
                    tp2=tp2,
                    stop_loss=stop_loss,
                    rsi=rsi,
                    volume_vs_avg=volume_ratio,
                    market_regime=market_regime,
                    has_position=True,  # Changed to True to show all 4 enhanced features
                    shares=100
                )

                # Add to results
                results['enhanced_features'] = enhanced_results

        except Exception as e:
            logger.warning(f"Enhanced features error: {e}")
            import traceback
            logger.warning(f"Traceback: {traceback.format_exc()}")
            results['enhanced_features'] = None

        # 🆕 v5.0 + v5.1: Extract intelligent features to top-level for easy frontend access
        if 'unified_recommendation' in results:
            unified = results['unified_recommendation']

            # Extract immediate entry info
            if 'immediate_entry_info' in unified:
                results['immediate_entry_info'] = unified['immediate_entry_info']
                logger.info(f"🆕 Added immediate_entry_info to top-level: {unified['immediate_entry_info'].get('immediate_entry')}")

            # Extract entry levels
            if 'entry_levels' in unified:
                results['entry_levels'] = unified['entry_levels']
                logger.info(f"🆕 Added entry_levels to top-level (method: {unified['entry_levels'].get('method')})")

            # Extract TP levels
            if 'tp_levels' in unified:
                results['tp_levels'] = unified['tp_levels']
                logger.info(f"🆕 Added tp_levels to top-level (method: {unified['tp_levels'].get('method')})")

            # Extract SL details
            if 'sl_details' in unified:
                results['sl_details'] = unified['sl_details']
                logger.info(f"🆕 Added sl_details to top-level (method: {unified['sl_details'].get('method')})")

            # Extract swing points
            if 'swing_points' in unified:
                results['swing_points'] = unified['swing_points']
                logger.info(f"🆕 Added swing_points to top-level: high={unified['swing_points'].get('swing_high')}, low={unified['swing_points'].get('swing_low')}")

        # Clean results for JSON serialization
        cleaned_results = clean_analysis_results(results)

        # DEBUG: Log after cleaning
        cleaned_unified_rec = cleaned_results.get('unified_recommendation', {})
        cleaned_weights = cleaned_unified_rec.get('weights_applied', {})
        logger.info(f"🔍 API DEBUG (after clean) - weights_applied: {cleaned_weights}")
        logger.info(f"🆕 Top-level v5.0+v5.1 fields present: immediate_entry={('immediate_entry_info' in cleaned_results)}, entry_levels={('entry_levels' in cleaned_results)}, tp_levels={('tp_levels' in cleaned_results)}")

        return jsonify(cleaned_results)

    except Exception as e:
        logger.error(f"Analysis API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/screen', methods=['POST'])
def api_screen():
    """API endpoint for stock screening"""
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])
        criteria = data.get('criteria', {})

        if not symbols:
            return jsonify({'error': 'Symbols are required'}), 400

        # Perform screening
        results = analyzer.screen_stocks(symbols, criteria)

        # Clean results for JSON serialization
        cleaned_results = clean_analysis_results(results)

        return jsonify(cleaned_results)

    except Exception as e:
        logger.error(f"Screening API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/support-screen', methods=['POST'])
def api_support_screen():
    """API endpoint for support level screening"""
    try:
        data = request.get_json()

        # Extract criteria
        max_distance_from_support = data.get('max_distance_from_support', 0.05)
        min_fundamental_score = data.get('min_fundamental_score', 5.0)
        min_technical_score = data.get('min_technical_score', 4.0)
        min_momentum_score = data.get('min_momentum_score', 5.0)
        max_stocks = data.get('max_stocks', 10)
        time_horizon = data.get('time_horizon', 'medium')

        # Run support level screening
        opportunities = support_screener.screen_support_opportunities(
            max_distance_from_support=max_distance_from_support,
            min_fundamental_score=min_fundamental_score,
            min_technical_score=min_technical_score,
            min_momentum_score=min_momentum_score,
            max_stocks=max_stocks,
            time_horizon=time_horizon
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': "AI-generated universe",
            'found_opportunities': len(opportunities),
            'criteria': {
                'max_distance_from_support': max_distance_from_support,
                'min_fundamental_score': min_fundamental_score,
                'min_technical_score': min_technical_score,
                'min_momentum_score': min_momentum_score,
                'max_stocks': max_stocks,
                'time_horizon': time_horizon
            }
        })

    except Exception as e:
        logger.error(f"Support screening API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/premarket-scan', methods=['POST'])
def api_premarket_scan():
    """API endpoint for pre-market gap scanning"""
    try:
        data = request.get_json()

        # Extract criteria
        min_gap_pct = data.get('min_gap_pct', 2.0)
        max_gap_pct = data.get('max_gap_pct', 4.0)  # v8.0: Expanded to 2-4% range
        min_volume_ratio = data.get('min_volume_ratio', 3.0)
        min_price = data.get('min_price', 5.0)
        market_caps = data.get('market_caps', ['large', 'mid'])
        prioritize_tech = data.get('prioritize_tech', True)
        max_stocks = data.get('max_stocks', 20)

        # Run pre-market scan (demo_mode auto-enabled outside pre-market hours)
        scan_result = premarket_scanner.scan_premarket_opportunities(
            min_gap_pct=min_gap_pct,
            max_gap_pct=max_gap_pct,
            min_volume_ratio=min_volume_ratio,
            min_price=min_price,
            market_caps=market_caps,
            prioritize_tech=prioritize_tech,
            max_stocks=max_stocks,
            demo_mode=False  # Will auto-enable if not in pre-market hours
        )

        # Extract results from scanner
        opportunities = scan_result['opportunities']
        demo_mode_active = scan_result['demo_mode']
        market_state = scan_result['market_state']

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': "AI-generated universe",
            'found_opportunities': len(opportunities),
            'demo_mode': demo_mode_active,
            'market_state': market_state,
            'criteria': {
                'min_gap_pct': min_gap_pct,
                'max_gap_pct': max_gap_pct,
                'min_volume_ratio': min_volume_ratio,
                'min_price': min_price,
                'market_caps': market_caps,
                'prioritize_tech': prioritize_tech,
                'max_stocks': max_stocks
            }
        })

    except Exception as e:
        logger.error(f"Pre-market scanning API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chart-data/<symbol>')
def api_chart_data(symbol):
    """API endpoint for chart data - adjusts range based on time horizon"""
    try:
        # Get time_horizon parameter (default: medium)
        time_horizon = request.args.get('time_horizon', 'medium')

        # Map time horizon to period and trading days
        horizon_mapping = {
            'swing': {'period': '2mo', 'days': 42},      # 2 months for swing trading (1-7 days)
            'short': {'period': '3mo', 'days': 63},      # 3 months for short-term
            'medium': {'period': '1y', 'days': 252},     # 1 year for medium-term
            'long': {'period': '2y', 'days': 504}        # 2 years for long-term
        }

        # Get mapping or use default (medium)
        config = horizon_mapping.get(time_horizon, horizon_mapping['medium'])

        # Get price data for charts
        price_data = analyzer.data_manager.get_price_data(symbol.upper(), period=config['period'])

        if price_data is None or price_data.empty:
            return jsonify({'error': 'No price data available'}), 404

        # Convert to chart format - limit to specified days
        price_data = price_data.tail(config['days'])

        # Prepare dates
        try:
            dates = [date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date) for date in price_data.index]
        except:
            dates = list(range(len(price_data)))

        # Prepare price data with safe column access
        def safe_column(df, col_name, default_name=None):
            possible_names = [col_name, col_name.lower(), col_name.upper()]
            if default_name:
                possible_names.append(default_name)

            for name in possible_names:
                if name in df.columns:
                    return df[name].fillna(0).tolist()
            return [0] * len(df)

        chart_data = {
            'dates': dates,
            'prices': {
                'open': safe_column(price_data, 'Open'),
                'high': safe_column(price_data, 'High'),
                'low': safe_column(price_data, 'Low'),
                'close': safe_column(price_data, 'Close'),
            },
            'volume': safe_column(price_data, 'Volume')
        }

        return jsonify(chart_data)

    except Exception as e:
        logger.error(f"Chart data API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/trending-stocks', methods=['POST'])
def api_trending_stocks():
    """API endpoint for trending stocks"""
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])

        if not symbols:
            return jsonify({'error': 'No symbols provided'}), 400

        trending_stocks = []

        for symbol in symbols[:8]:  # Limit to 8 stocks
            try:
                # Get basic price data
                price_data = analyzer.data_manager.get_price_data(symbol.upper(), period='5d')

                if price_data is not None and not price_data.empty and len(price_data) >= 2:
                    # Check available columns and use appropriate names
                    close_col = None
                    volume_col = None

                    for col in price_data.columns:
                        if col.lower() in ['close', 'adj close', 'adjclose']:
                            close_col = col
                        elif col.lower() in ['volume', 'vol']:
                            volume_col = col

                    if close_col is not None:
                        current_price = float(price_data[close_col].iloc[-1])
                        prev_price = float(price_data[close_col].iloc[-2])
                        change = current_price - prev_price
                        change_percent = (change / prev_price) * 100

                        trending_stocks.append({
                            'symbol': symbol.upper(),
                            'current_price': current_price,
                            'change': change,
                            'change_percent': change_percent,
                            'volume': float(price_data[volume_col].iloc[-1]) if volume_col is not None else 0
                        })
                    else:
                        logger.warning(f"No close price column found for {symbol}. Available columns: {list(price_data.columns)}")

            except Exception as e:
                logger.warning(f"Failed to get data for {symbol}: {e}")
                continue

        # Sort by absolute change percentage (most volatile first)
        trending_stocks.sort(key=lambda x: abs(x['change_percent']), reverse=True)

        return jsonify({
            'trending_stocks': trending_stocks,
            'total_count': len(trending_stocks)
        })

    except Exception as e:
        logger.error(f"Trending stocks API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/backtest', methods=['POST'])
def api_backtest():
    """API endpoint for backtesting"""
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])
        start_date = data.get('start_date', '2023-01-01')
        end_date = data.get('end_date', '2024-01-01')
        initial_capital = data.get('initial_capital', 100000)

        if not symbols:
            return jsonify({'error': 'Symbols are required'}), 400

        # Run backtest
        results = analyzer.run_backtest(
            symbols, start_date=start_date,
            end_date=end_date, initial_capital=initial_capital
        )

        # Clean results for JSON serialization
        cleaned_results = clean_analysis_results(results)

        return jsonify(cleaned_results)

    except Exception as e:
        logger.error(f"Backtest API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market-data')
def api_market_data():
    """API endpoint for market overview data"""
    try:
        # Get market overview
        major_indices = ['SPY', 'QQQ', 'IWM', 'VTI']
        market_data = analyzer.data_manager.get_multiple_symbols(
            major_indices, data_type='realtime'
        )

        return jsonify(market_data)

    except Exception as e:
        logger.error(f"Market data API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/suggestions/<query>')
def api_suggestions(query):
    """API endpoint for symbol suggestions"""
    try:
        # Simple symbol suggestions (in practice, this would query a symbols database)
        common_symbols = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
            'DIS', 'PYPL', 'ADBE', 'CRM', 'ORCL', 'INTC', 'AMD', 'UBER',
            'SPY', 'QQQ', 'IWM', 'VTI', 'VOO', 'VEA', 'VWO', 'BND'
        ]

        # Filter symbols that start with query
        suggestions = [s for s in common_symbols if s.startswith(query.upper())][:10]

        return jsonify({'suggestions': suggestions})

    except Exception as e:
        logger.error(f"Suggestions API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dividend-screen', methods=['POST'])
def api_dividend_screen():
    """API endpoint for dividend growth screening"""
    try:
        data = request.get_json()

        # Extract criteria
        min_dividend_yield = data.get('min_dividend_yield', 3.0)
        min_dividend_growth_rate = data.get('min_dividend_growth_rate', 5.0)
        min_payout_ratio = data.get('min_payout_ratio', 30.0)
        max_payout_ratio = data.get('max_payout_ratio', 70.0)
        min_fundamental_score = data.get('min_fundamental_score', 5.0)
        max_stocks = data.get('max_stocks', 15)

        # Run dividend screening
        opportunities = dividend_screener.screen_dividend_opportunities(
            min_dividend_yield=min_dividend_yield,
            min_dividend_growth_rate=min_dividend_growth_rate,
            min_payout_ratio=min_payout_ratio,
            max_payout_ratio=max_payout_ratio,
            min_fundamental_score=min_fundamental_score,
            max_stocks=max_stocks,
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': "AI-generated universe",
            'found_opportunities': len(opportunities),
            'criteria': {
                'min_dividend_yield': min_dividend_yield,
                'min_dividend_growth_rate': min_dividend_growth_rate,
                'min_payout_ratio': min_payout_ratio,
                'max_payout_ratio': max_payout_ratio,
                'min_fundamental_score': min_fundamental_score,
                'max_stocks': max_stocks,
            }
        })

    except Exception as e:
        logger.error(f"Dividend screening API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai-dividend-screen', methods=['POST'])
def api_ai_dividend_screen():
    """API endpoint for AI-powered dividend growth screening"""
    try:
        data = request.get_json()

        # Extract criteria
        min_dividend_yield = data.get('min_dividend_yield', 3.0)
        min_dividend_growth_rate = data.get('min_dividend_growth_rate', 5.0)
        min_payout_ratio = data.get('min_payout_ratio', 30.0)
        max_payout_ratio = data.get('max_payout_ratio', 70.0)
        min_fundamental_score = data.get('min_fundamental_score', 5.0)
        max_stocks = data.get('max_stocks', 15)

        logger.info(f"🤖 Starting AI-powered dividend screening with {max_stocks} target stocks")

        # Run AI-powered dividend screening
        opportunities = dividend_screener.screen_dividend_opportunities(
            min_dividend_yield=min_dividend_yield,
            min_dividend_growth_rate=min_dividend_growth_rate,
            min_payout_ratio=min_payout_ratio,
            max_payout_ratio=max_payout_ratio,
            min_fundamental_score=min_fundamental_score,
            max_stocks=max_stocks,
            use_ai_universe=True  # Force AI universe generation
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': 'AI-generated universe',
            'found_opportunities': len(opportunities),
            'ai_powered': True,
            'criteria': {
                'min_dividend_yield': min_dividend_yield,
                'min_dividend_growth_rate': min_dividend_growth_rate,
                'min_payout_ratio': min_payout_ratio,
                'max_payout_ratio': max_payout_ratio,
                'min_fundamental_score': min_fundamental_score,
                'max_stocks': max_stocks,
            }
        })

    except Exception as e:
        logger.error(f"AI Dividend screening API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-support-screen', methods=['POST'])
def api_ai_support_screen():
    """API endpoint for AI-powered support level screening"""
    try:
        data = request.get_json()

        # Extract criteria
        max_distance_from_support = data.get('max_distance_from_support', 0.05)
        min_fundamental_score = data.get('min_fundamental_score', 5.0)
        min_technical_score = data.get('min_technical_score', 4.0)
        min_momentum_score = data.get('min_momentum_score', 5.0)
        max_stocks = data.get('max_stocks', 10)
        time_horizon = data.get('time_horizon', 'medium')

        logger.info(f"🤖 Starting AI-powered support level screening with {max_stocks} target stocks")

        # Run AI-powered support level screening
        opportunities = support_screener.screen_support_opportunities(
            max_distance_from_support=max_distance_from_support,
            min_fundamental_score=min_fundamental_score,
            min_technical_score=min_technical_score,
            min_momentum_score=min_momentum_score,
            max_stocks=max_stocks,
            time_horizon=time_horizon,
            use_ai_universe=True  # Force AI universe generation
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': 'AI-generated universe',
            'found_opportunities': len(opportunities),
            'ai_powered': True,
            'criteria': {
                'max_distance_from_support': max_distance_from_support,
                'min_fundamental_score': min_fundamental_score,
                'min_technical_score': min_technical_score,
                'min_momentum_score': min_momentum_score,
                'max_stocks': max_stocks,
                'time_horizon': time_horizon
            }
        })

    except Exception as e:
        logger.error(f"AI Support level screening API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/value-screen', methods=['POST'])
def api_value_screen():
    """API endpoint for value stock screening"""
    try:
        data = request.get_json()

        # Extract criteria
        max_pe_ratio = data.get('max_pe_ratio', 15.0)
        max_pb_ratio = data.get('max_pb_ratio', 3.0)
        min_roe = data.get('min_roe', 10.0)
        max_debt_to_equity = data.get('max_debt_to_equity', 0.5)
        min_fundamental_score = data.get('min_fundamental_score', 5.0)
        min_technical_score = data.get('min_technical_score', 4.0)
        max_stocks = data.get('max_stocks', 15)
        screen_type = data.get('screen_type', 'value')  # 'value' or 'undervalued_growth'
        time_horizon = data.get('time_horizon', 'long')

        logger.info(f"🔍 Starting {screen_type} screening with {max_stocks} target stocks")

        # Run value screening
        opportunities = value_screener.screen_value_opportunities(
            max_pe_ratio=max_pe_ratio,
            max_pb_ratio=max_pb_ratio,
            min_roe=min_roe,
            max_debt_to_equity=max_debt_to_equity,
            min_fundamental_score=min_fundamental_score,
            min_technical_score=min_technical_score,
            max_stocks=max_stocks,
            screen_type=screen_type,
            time_horizon=time_horizon
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': 'AI-generated universe',
            'found_opportunities': len(opportunities),
            'screen_type': screen_type,
            'criteria': {
                'max_pe_ratio': max_pe_ratio,
                'max_pb_ratio': max_pb_ratio,
                'min_roe': min_roe,
                'max_debt_to_equity': max_debt_to_equity,
                'min_fundamental_score': min_fundamental_score,
                'min_technical_score': min_technical_score,
                'max_stocks': max_stocks,
                'screen_type': screen_type,
                'time_horizon': time_horizon
            }
        })

    except Exception as e:
        logger.error(f"Value screening API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-value-screen', methods=['POST'])
def api_ai_value_screen():
    """API endpoint for AI-powered value stock screening"""
    try:
        data = request.get_json()

        # Extract criteria
        max_pe_ratio = data.get('max_pe_ratio', 15.0)
        max_pb_ratio = data.get('max_pb_ratio', 3.0)
        min_roe = data.get('min_roe', 10.0)
        max_debt_to_equity = data.get('max_debt_to_equity', 0.5)
        min_fundamental_score = data.get('min_fundamental_score', 5.0)
        min_technical_score = data.get('min_technical_score', 4.0)
        max_stocks = data.get('max_stocks', 15)
        screen_type = data.get('screen_type', 'value')  # 'value' or 'undervalued_growth'
        time_horizon = data.get('time_horizon', 'long')

        logger.info(f"🤖 Starting AI-powered {screen_type} screening with {max_stocks} target stocks")

        # Run AI-powered value screening (force AI universe generation)
        opportunities = value_screener.screen_value_opportunities(
            max_pe_ratio=max_pe_ratio,
            max_pb_ratio=max_pb_ratio,
            min_roe=min_roe,
            max_debt_to_equity=max_debt_to_equity,
            min_fundamental_score=min_fundamental_score,
            min_technical_score=min_technical_score,
            max_stocks=max_stocks,
            screen_type=screen_type,
            time_horizon=time_horizon
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': 'AI-generated universe',
            'found_opportunities': len(opportunities),
            'ai_powered': True,
            'screen_type': screen_type,
            'criteria': {
                'max_pe_ratio': max_pe_ratio,
                'max_pb_ratio': max_pb_ratio,
                'min_roe': min_roe,
                'max_debt_to_equity': max_debt_to_equity,
                'min_fundamental_score': min_fundamental_score,
                'min_technical_score': min_technical_score,
                'max_stocks': max_stocks,
                'screen_type': screen_type,
                'time_horizon': time_horizon
            }
        })

    except Exception as e:
        logger.error(f"AI Value screening API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/smallmid-screen', methods=['POST'])
def api_smallmid_screen():
    """API endpoint for Small/Mid Cap growth screening"""
    try:
        data = request.get_json()

        # Extract criteria
        market_cap_type = data.get('market_cap_type', 'both')
        min_revenue_growth = data.get('min_revenue_growth', 10.0)
        min_earnings_growth = data.get('min_earnings_growth', 10.0)
        min_momentum_score = data.get('min_momentum_score', 4.0)
        volume_trend = data.get('volume_trend', 'any')
        min_fundamental_score = data.get('min_fundamental_score', 3.0)
        min_technical_score = data.get('min_technical_score', 3.0)
        max_stocks = data.get('max_stocks', 12)
        time_horizon = data.get('time_horizon', 'medium')

        logger.info(f"🚀 Starting Small/Mid Cap growth screening ({market_cap_type}) with {max_stocks} target stocks")

        # Run Small/Mid Cap growth screening
        opportunities = value_screener.screen_small_mid_cap_opportunities(
            market_cap_type=market_cap_type,
            min_revenue_growth=min_revenue_growth,
            min_earnings_growth=min_earnings_growth,
            min_momentum_score=min_momentum_score,
            volume_trend=volume_trend,
            min_fundamental_score=min_fundamental_score,
            min_technical_score=min_technical_score,
            max_stocks=max_stocks,
            time_horizon=time_horizon
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': 'AI-generated universe',
            'found_opportunities': len(opportunities),
            'market_cap_type': market_cap_type,
            'criteria': {
                'market_cap_type': market_cap_type,
                'min_revenue_growth': min_revenue_growth,
                'min_earnings_growth': min_earnings_growth,
                'min_momentum_score': min_momentum_score,
                'volume_trend': volume_trend,
                'min_fundamental_score': min_fundamental_score,
                'min_technical_score': min_technical_score,
                'max_stocks': max_stocks,
                'time_horizon': time_horizon
            }
        })

    except Exception as e:
        logger.error(f"Small/Mid Cap screening API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/market-analysis', methods=['GET'])
def api_market_analysis():
    """API endpoint for AI market analysis"""
    try:
        logger.info("Generating AI market analysis...")
        analysis = market_analyst.generate_market_analysis()

        logger.info(f"Market analysis generated successfully. Success: {analysis.get('success', False)}")
        return jsonify(analysis)

    except Exception as e:
        logger.error(f"Market analysis API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'generated_at': datetime.now().strftime("%Y-%m-%d"),
            'analysis_period': '1-3 เดือนข้างหน้า',
            'market_summary': f'เกิดข้อผิดพลาด: {str(e)}',
            'key_events': []
        }), 500

@app.route('/api/additional-events', methods=['GET'])
def api_additional_events():
    """API endpoint for additional market events (rank 6-10)"""
    try:
        logger.info("Generating additional market events...")
        additional = market_analyst.generate_additional_events()

        logger.info(f"Additional events generated successfully. Success: {additional.get('success', False)}")
        return jsonify(additional)

    except Exception as e:
        logger.error(f"Additional events API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'generated_at': datetime.now().strftime("%Y-%m-%d"),
            'analysis_period': '1-3 เดือนข้างหน้า',
            'additional_events': []
        }), 500

@app.route('/api/market-insight', methods=['GET'])
def api_market_insight():
    """API endpoint for quick market insight"""
    try:
        logger.info("Generating quick market insight...")
        insight = market_analyst.generate_quick_market_insight()

        logger.info(f"Market insight generated successfully. Success: {insight.get('success', False)}")
        return jsonify(insight)

    except Exception as e:
        logger.error(f"Market insight API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'date': datetime.now().strftime("%Y-%m-%d"),
            'market_overview': f'เกิดข้อผิดพลาด: {str(e)}',
            'key_factors': [],
            'investor_advice': 'กรุณาลองใหม่อีกครั้ง'
        }), 500

@app.route('/api/stock-news', methods=['POST'])
def api_stock_news():
    """API endpoint for important stock news and price impact analysis"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        timeframe = data.get('timeframe', '1-3_months')

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        logger.info(f"Fetching important news for {symbol} with timeframe {timeframe}")

        # Create news analyzer
        from stock_news_analyzer import StockNewsAnalyzer
        news_analyzer = StockNewsAnalyzer()

        # Get important news and impact analysis
        news_data = news_analyzer.get_important_news_with_impact(symbol, timeframe)

        logger.info(f"News data generated for {symbol}. Found {len(news_data.get('news', []))} news items")
        return jsonify(news_data)

    except Exception as e:
        logger.error(f"Stock news API error: {e}")
        return jsonify({
            'error': f'เกิดข้อผิดพลาดในการดึงข่าว: {str(e)}',
            'symbol': symbol if 'symbol' in locals() else '',
            'news': []
        }), 500

@app.route('/api/enhanced-analysis', methods=['POST'])
def api_enhanced_analysis():
    """API endpoint for enhanced Yahoo Finance + AI analysis"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        logger.info(f"Starting enhanced analysis for {symbol}")

        # Get earnings and analyst data from Yahoo Enhanced Client
        earnings_analyzer = EarningsAnalystAnalyzer(symbol)
        yahoo_analysis = earnings_analyzer.get_comprehensive_analysis()

        # Get SEC EDGAR insider/institutional data
        from analysis.fundamental.insider_institutional import InsiderInstitutionalAnalyzer
        insider_analyzer = InsiderInstitutionalAnalyzer(symbol)
        sec_edgar_data = insider_analyzer.get_comprehensive_analysis()

        # Get AI analysis
        ai_analysis = analyzer.analyze_stock(symbol, 'medium', 100000)

        # Extract AI scores from the correct structure
        fundamental_score = ai_analysis.get('fundamental_analysis', {}).get('overall_score', 0)
        technical_score = ai_analysis.get('technical_analysis', {}).get('technical_score', {}).get('total_score', 0)

        # Extract AI-specific data from enhanced analysis
        ai_data = ai_analysis.get('ai_analysis', {})
        ai_summary = ai_data.get('analysis_summary', {})

        # Extract enhanced_analysis which contains price_change_analysis
        enhanced_analysis_data = ai_analysis.get('enhanced_analysis', {})
        price_change_analysis = enhanced_analysis_data.get('price_change_analysis', {})

        # Combine the analyses
        enhanced_result = {
            'symbol': symbol,
            'yahoo_data': yahoo_analysis,
            'sec_edgar_data': sec_edgar_data,
            'ai_analysis': {
                'overall_score': ai_summary.get('overall_score', (fundamental_score + technical_score) / 2 if fundamental_score or technical_score else 0),
                'recommendation': ai_summary.get('recommendation', ai_analysis.get('recommendation', 'hold')),
                'fundamental_score': fundamental_score,
                'technical_score': technical_score,
                'risk_score': round(10 - (ai_analysis.get('risk_assessment', {}).get('overall_risk_score', 0.5) * 10), 1),  # Convert 0-1 to 0-10 and invert
                'key_insights': ai_data.get('key_insights', ai_analysis.get('key_insights', [])),
                'price_target': ai_data.get('price_targets', {}).get('average_target', {}).get('price', 0),
                'stop_loss': ai_data.get('price_targets', {}).get('stop_loss', {}).get('price', 0)
            },
            'enhanced_analysis': {
                'price_change_analysis': price_change_analysis
            },
            'timestamp': datetime.now().isoformat(),
            'has_real_data': yahoo_analysis.get('has_real_data', False) or sec_edgar_data.get('has_real_data', False),
            'data_quality': yahoo_analysis.get('data_quality', 'limited')
        }

        # Clean results for JSON serialization
        cleaned_result = clean_analysis_results(enhanced_result)

        return jsonify(cleaned_result)

    except Exception as e:
        logger.error(f"Enhanced analysis API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sec-edgar-test', methods=['POST'])
def api_sec_edgar_test():
    """Test endpoint for SEC EDGAR data only"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        logger.info(f"Testing SEC EDGAR for {symbol}")

        # Get SEC EDGAR insider/institutional data only
        from analysis.fundamental.insider_institutional import InsiderInstitutionalAnalyzer
        insider_analyzer = InsiderInstitutionalAnalyzer(symbol)
        sec_edgar_data = insider_analyzer.get_comprehensive_analysis()

        return jsonify({
            'symbol': symbol,
            'sec_edgar_data': sec_edgar_data,
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        })

    except Exception as e:
        logger.error(f"SEC EDGAR test API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/volatile-screen', methods=['POST'])
def api_volatile_screen():
    """API endpoint for volatile trading screening"""
    try:
        data = request.get_json()

        # Extract criteria (updated defaults - more realistic)
        min_volatility = data.get('min_volatility', 35.0)
        min_avg_volume = data.get('min_avg_volume', 2000000)
        min_price_range = data.get('min_price_range', 8.0)
        min_momentum_score = data.get('min_momentum_score', 3.5)
        max_stocks = data.get('max_stocks', 20)
        time_horizon = data.get('time_horizon', 'short')

        # New parameters
        min_atr_pct = data.get('min_atr_pct', 2.0)
        min_price = data.get('min_price', 5.0)

        # Advanced filters
        exclude_falling_knife = data.get('exclude_falling_knife', True)
        exclude_overextended = data.get('exclude_overextended', False)
        only_uptrend = data.get('only_uptrend', False)
        require_dip = data.get('require_dip', False)

        logger.info(f"🚀 Starting volatile trading screening with {max_stocks} target stocks")
        logger.info(f"   Volatility: {min_volatility}%+, ATR%: {min_atr_pct}%+, Price: ${min_price}+")
        logger.info(f"   Filters: Falling Knife={not exclude_falling_knife}, Overextended={not exclude_overextended}, Uptrend Only={only_uptrend}, Require Dip={require_dip}")

        # Run volatile trading screening
        opportunities = value_screener.screen_volatile_trading_opportunities(
            min_volatility=min_volatility,
            min_avg_volume=min_avg_volume,
            min_price_range=min_price_range,
            min_momentum_score=min_momentum_score,
            max_stocks=max_stocks,
            time_horizon=time_horizon,
            min_atr_pct=min_atr_pct,
            min_price=min_price,
            exclude_falling_knife=exclude_falling_knife,
            exclude_overextended=exclude_overextended,
            only_uptrend=only_uptrend,
            require_dip=require_dip
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': 'AI-generated universe',
            'found_opportunities': len(opportunities),
            'criteria': {
                'min_volatility': min_volatility,
                'min_avg_volume': min_avg_volume,
                'min_price_range': min_price_range,
                'min_momentum_score': min_momentum_score,
                'max_stocks': max_stocks,
                'time_horizon': time_horizon
            }
        })

    except Exception as e:
        logger.error(f"Volatile trading screening API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/growth-catalyst-screen', methods=['POST'])
def api_growth_catalyst_screen():
    """API endpoint for 14-day growth catalyst screening"""
    try:
        data = request.get_json()

        # Extract criteria
        target_gain_pct = data.get('target_gain_pct', 15.0)
        timeframe_days = data.get('timeframe_days', 30)
        min_market_cap = data.get('min_market_cap', 500_000_000)  # $500M
        max_market_cap = data.get('max_market_cap', None)  # No limit
        min_price = data.get('min_price', 3.0)  # v3.2 Tiered: $3+ with strict quality for low price
        max_price = data.get('max_price', 2000.0)  # Allow high-value stocks
        min_daily_volume = data.get('min_daily_volume', 10_000_000)  # $10M
        min_catalyst_score = data.get('min_catalyst_score', 0.0)  # v4.0: Inverted scoring, 0+ recommended
        min_technical_score = data.get('min_technical_score', 0.0)  # v4.0: Momentum gates filter first
        min_ai_probability = data.get('min_ai_probability', 0.0)  # v4.0: Momentum gates filter first
        min_entry_score = data.get('min_entry_score', 55.0)  # v4.0: Quality Filter - 55+ recommended
        max_stocks = data.get('max_stocks', 20)
        universe_multiplier = data.get('universe_multiplier', 5)  # v7.1: Match UI default (5x = 150 stocks)

        logger.info(f"🎯 Starting 14-Day Growth Catalyst screening")
        logger.info(f"   Target: {target_gain_pct}%+ gain in {timeframe_days} days")
        logger.info(f"   Filters: Catalyst≥{min_catalyst_score}, Technical≥{min_technical_score}, AI Prob≥{min_ai_probability}%, Entry Score≥{min_entry_score}")

        # Run growth catalyst screening
        opportunities = growth_catalyst_screener.screen_growth_catalyst_opportunities(
            target_gain_pct=target_gain_pct,
            timeframe_days=timeframe_days,
            min_market_cap=min_market_cap,
            max_market_cap=max_market_cap,
            min_price=min_price,
            max_price=max_price,
            min_daily_volume=min_daily_volume,
            min_catalyst_score=min_catalyst_score,
            min_technical_score=min_technical_score,
            min_ai_probability=min_ai_probability,
            max_stocks=max_stocks,
            universe_multiplier=universe_multiplier
        )

        # v6.5: Filter by Momentum Score (Sweet Spot Scoring - max 100)
        # Backtest showed momentum_score >= 88 with Top 1 = 100% WR!
        if min_entry_score > 0 and opportunities:
            before_count = len(opportunities)
            # Use momentum_score (Sweet Spot) instead of entry_score (includes bonuses)
            opportunities = [opp for opp in opportunities if opp.get('momentum_score', 0) >= min_entry_score]
            after_count = len(opportunities)
            if before_count > after_count:
                logger.info(f"   🎯 Momentum Score (Sweet Spot) filter: {before_count} → {after_count} stocks (filtered {before_count - after_count} stocks with Momentum Score < {min_entry_score})")

        # v6.5: Sort by Momentum Score (Sweet Spot) - higher is better
        if opportunities:
            def sort_key(opp):
                # Get sector regime (BULL, SIDEWAYS, BEAR, etc.)
                sector_regime = opp.get('sector_regime', 'UNKNOWN')
                momentum_score = opp.get('momentum_score', 0)

                # Priority: BULL = 0, SIDEWAYS = 1, others = 2
                if 'BULL' in sector_regime.upper():
                    regime_priority = 0
                elif 'SIDEWAYS' in sector_regime.upper():
                    regime_priority = 1
                else:
                    regime_priority = 2

                # Sort by regime priority first (ascending), then momentum_score (descending)
                return (regime_priority, -momentum_score)

            opportunities.sort(key=sort_key)
            logger.info(f"   📊 Sorted by BULL sectors first, then Momentum Score")

        # NEW: Check for regime warning
        if opportunities and len(opportunities) > 0 and opportunities[0].get('regime_warning'):
            regime_data = opportunities[0]
            logger.warning(f"⚠️ Market regime filter: {regime_data['regime']} - not suitable for trading")

            return jsonify({
                'regime_warning': True,
                'regime': regime_data['regime'],
                'regime_strength': regime_data['regime_strength'],
                'message': regime_data['message'],
                'recommendation': regime_data['recommendation'],
                'details': regime_data.get('details', {}),
                'opportunities': [],
                'found_opportunities': 0,
                'criteria': {
                    'target_gain_pct': target_gain_pct,
                    'timeframe_days': timeframe_days,
                }
            })

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        # Extract regime info if available
        regime_info = None
        sector_regime_summary = None
        if opportunities and len(opportunities) > 0:
            if 'regime_info' in opportunities[0]:
                regime_info = opportunities[0]['regime_info']
            # v3.3: Extract sector regime summary
            if 'sector_regime_summary' in opportunities[0]:
                sector_regime_summary = opportunities[0]['sector_regime_summary']

        return jsonify({
            'opportunities': cleaned_opportunities,
            'regime_info': regime_info,  # Market regime info
            'sector_regime_summary': sector_regime_summary,  # v3.3: Sector regime summary
            'total_screened': 'AI-generated universe',
            'found_opportunities': len(opportunities),
            'criteria': {
                'target_gain_pct': target_gain_pct,
                'timeframe_days': timeframe_days,
                'min_market_cap': min_market_cap,
                'max_market_cap': max_market_cap,
                'min_price': min_price,
                'max_price': max_price,
                'min_daily_volume': min_daily_volume,
                'min_catalyst_score': min_catalyst_score,
                'min_technical_score': min_technical_score,
                'min_ai_probability': min_ai_probability,
                'max_stocks': max_stocks,
                'universe_multiplier': universe_multiplier
            }
        })

    except Exception as e:
        logger.error(f"Growth catalyst screening API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/momentum-growth-screen', methods=['POST'])
def api_momentum_growth_screen():
    """API endpoint for Momentum-Based Growth screening (RELAXED filters)"""
    try:
        data = request.get_json()

        # Extract criteria - RELAXED configuration from backtest winner
        min_rsi = data.get('min_rsi', 35.0)
        max_rsi = data.get('max_rsi', 70.0)
        min_price_above_ma20 = data.get('min_price_above_ma20', -2.0)
        min_price_above_ma50 = data.get('min_price_above_ma50', -5.0)
        min_momentum_10d = data.get('min_momentum_10d', -2.0)
        min_momentum_30d = data.get('min_momentum_30d', 5.0)
        min_market_cap = data.get('min_market_cap', 1_000_000_000)  # $1B
        min_price = data.get('min_price', 5.0)
        max_price = data.get('max_price', 500.0)
        min_volume = data.get('min_volume', 500_000)
        max_stocks = data.get('max_stocks', 20)
        universe_size = data.get('universe_size', 100)

        logger.info(f"🎯 Starting Momentum Growth Screening (RELAXED)")
        logger.info(f"   Filters: RSI {min_rsi}-{max_rsi}, MA20 >{min_price_above_ma20}%, MA50 >{min_price_above_ma50}%")
        logger.info(f"   Momentum: 10d >{min_momentum_10d}%, 30d >{min_momentum_30d}%")

        # Run momentum screening
        opportunities = momentum_growth_screener.screen_opportunities(
            min_rsi=min_rsi,
            max_rsi=max_rsi,
            min_price_above_ma20=min_price_above_ma20,
            min_price_above_ma50=min_price_above_ma50,
            min_momentum_10d=min_momentum_10d,
            min_momentum_30d=min_momentum_30d,
            min_market_cap=min_market_cap,
            min_price=min_price,
            max_price=max_price,
            min_volume=min_volume,
            max_stocks=max_stocks,
            universe_size=universe_size
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'total_screened': 'AI-generated universe',
            'found_opportunities': len(opportunities),
            'screener_version': 'MomentumGrowth_v1.0_Relaxed',
            'criteria': {
                'min_rsi': min_rsi,
                'max_rsi': max_rsi,
                'min_price_above_ma20': min_price_above_ma20,
                'min_price_above_ma50': min_price_above_ma50,
                'min_momentum_10d': min_momentum_10d,
                'min_momentum_30d': min_momentum_30d,
                'min_market_cap': min_market_cap,
                'min_price': min_price,
                'max_price': max_price,
                'min_volume': min_volume,
                'max_stocks': max_stocks,
                'universe_size': universe_size
            }
        })

    except Exception as e:
        logger.error(f"Momentum growth screening API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai-second-opinion', methods=['POST'])
def api_ai_second_opinion():
    """API endpoint for AI Second Opinion (on-demand only)"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        time_horizon = data.get('time_horizon', 'medium')

        # Get cached analysis results if provided
        cached_analysis = data.get('cached_analysis')

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        logger.info(f"🤖 Generating AI Second Opinion for {symbol} (on-demand)")

        # If cached analysis provided, use it; otherwise analyze fresh
        if cached_analysis:
            analysis_results = cached_analysis
            logger.info(f"Using cached analysis for {symbol}")
        else:
            # Perform fresh analysis (without AI to save cost, will add AI Second Opinion separately)
            analysis_results = analyzer.analyze_stock(symbol, time_horizon, include_ai_analysis=False)
            logger.info(f"Performed fresh analysis for {symbol}")

        # Generate AI Second Opinion
        from ai_second_opinion import ai_second_opinion_service
        ai_opinion_result = ai_second_opinion_service.analyze(analysis_results)

        if ai_opinion_result.get('success'):
            ai_opinion = ai_opinion_result.get('ai_second_opinion')
            expectancy = ai_opinion.get('expectancy', {})
            logger.info(f"✅ Performance Expectancy calculated: Win Rate {expectancy.get('win_rate', 'N/A')}, Expectancy {expectancy.get('expectancy_per_trade', 'N/A')}")

            # Clean for JSON
            cleaned_opinion = clean_analysis_results(ai_opinion)

            return jsonify({
                'success': True,
                'symbol': symbol,
                'ai_second_opinion': cleaned_opinion
            })
        else:
            logger.warning(f"AI Second Opinion generation failed for {symbol}")
            return jsonify({
                'success': False,
                'error': 'AI Second Opinion generation failed',
                'symbol': symbol
            }), 500

    except Exception as e:
        logger.error(f"AI Second Opinion API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/portfolio')
def portfolio_page():
    """Portfolio monitoring page"""
    return render_template('portfolio.html')


@app.route('/drafts')
def drafts_page():
    """Draft stocks page - stocks found by auto scanner"""
    return render_template('drafts.html')


@app.route('/api/drafts', methods=['GET'])
def api_get_drafts():
    """Get all draft stocks"""
    try:
        drafts_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'draft_stocks.json')

        if os.path.exists(drafts_file):
            with open(drafts_file, 'r') as f:
                data = json.load(f)
            return jsonify(data)
        else:
            return jsonify({
                'last_update': None,
                'count': 0,
                'drafts': [],
                'message': 'No drafts yet. Start the auto scanner first.'
            })

    except Exception as e:
        logger.error(f"Get drafts error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/drafts/pick', methods=['POST'])
def api_pick_draft():
    """Pick a draft stock and add to portfolio"""
    try:
        from portfolio_manager_v3 import PortfolioManagerV3

        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        entry_price = data.get('entry_price')
        shares = data.get('shares')

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        # Load draft to get entry details
        drafts_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'draft_stocks.json')
        draft_data = None

        if os.path.exists(drafts_file):
            with open(drafts_file, 'r') as f:
                all_drafts = json.load(f)
                for d in all_drafts.get('drafts', []):
                    if d['symbol'] == symbol:
                        draft_data = d
                        break

        if not draft_data:
            return jsonify({'error': f'{symbol} not found in drafts'}), 404

        # Use draft entry price if not specified
        if not entry_price:
            entry_price = draft_data.get('entry_price', draft_data.get('current_price', 0))

        # Add to portfolio
        pm = PortfolioManagerV3()

        # Calculate stop and targets from draft
        stop_loss = draft_data.get('stop_loss', entry_price * 0.975)
        target1 = draft_data.get('target1', entry_price * 1.05)
        target2 = draft_data.get('target2', entry_price * 1.085)

        # Calculate amount from shares
        amount = (shares or 100) * entry_price

        success = pm.add_position(
            symbol=symbol,
            entry_price=entry_price,
            entry_date=datetime.now().strftime('%Y-%m-%d'),
            amount=amount,
        )

        if success:
            # Update draft status
            for d in all_drafts.get('drafts', []):
                if d['symbol'] == symbol:
                    d['status'] = 'PICKED'
                    d['picked_date'] = datetime.now().isoformat()
                    break

            with open(drafts_file, 'w') as f:
                json.dump(all_drafts, f, indent=2)

            return jsonify({
                'success': True,
                'symbol': symbol,
                'message': f'{symbol} added to portfolio'
            })
        else:
            return jsonify({'error': 'Failed to add to portfolio'}), 500

    except Exception as e:
        logger.error(f"Pick draft error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/drafts/remove', methods=['POST'])
def api_remove_draft():
    """Remove a draft stock"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        drafts_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'draft_stocks.json')

        if os.path.exists(drafts_file):
            with open(drafts_file, 'r') as f:
                all_drafts = json.load(f)

            original_count = len(all_drafts.get('drafts', []))
            all_drafts['drafts'] = [d for d in all_drafts.get('drafts', []) if d['symbol'] != symbol]

            if len(all_drafts['drafts']) < original_count:
                all_drafts['count'] = len(all_drafts['drafts'])
                with open(drafts_file, 'w') as f:
                    json.dump(all_drafts, f, indent=2)

                return jsonify({
                    'success': True,
                    'symbol': symbol,
                    'message': f'{symbol} removed from drafts'
                })

        return jsonify({'error': f'{symbol} not found in drafts'}), 404

    except Exception as e:
        logger.error(f"Remove draft error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/scanner/status', methods=['GET'])
def api_scanner_status():
    """Get auto scanner status"""
    try:
        status_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'logs', 'scanner_status.json')

        if os.path.exists(status_file):
            with open(status_file, 'r') as f:
                return jsonify(json.load(f))
        else:
            return jsonify({
                'running': False,
                'message': 'Scanner not started. Run: python src/auto_scanner_draft.py'
            })

    except Exception as e:
        logger.error(f"Scanner status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/status', methods=['GET'])
def api_portfolio_status():
    """Get current portfolio status with exit signals"""
    try:
        from portfolio_manager_v3 import PortfolioManagerV3
        from datetime import datetime

        # Initialize portfolio manager v3 (6-layer system)
        pm = PortfolioManagerV3()

        # Update positions with current prices
        current_date = datetime.now().strftime('%Y-%m-%d')
        updates = pm.update_positions(current_date)

        # Get regime info
        regime_info = None
        if pm.regime_detector:
            regime_info = pm.regime_detector.get_current_regime()

        # Get stats
        stats = pm.get_summary()

        # Format positions with exit signals
        positions_with_signals = []

        for pos in updates.get('holding', []):
            # Determine if should exit based on updates
            exit_signal = None

            # Check if in exit_positions list
            for exit_pos in updates.get('exit_positions', []):
                if exit_pos['symbol'] == pos['symbol']:
                    exit_signal = {
                        'should_exit': True,
                        'reason': exit_pos['exit_reason'],
                        'priority': 'CRITICAL' if 'STOP' in exit_pos['exit_reason'] or 'BEAR' in exit_pos['exit_reason'] else 'WARNING'
                    }
                    break

            positions_with_signals.append({
                'symbol': pos['symbol'],
                'entry_date': pos['entry_date'],
                'entry_price': pos['entry_price'],
                'current_price': pos.get('current_price', 0),
                'highest_price': pos.get('highest_price', pos['entry_price']),
                'pnl_pct': pos.get('pnl_pct', 0),
                'pnl_usd': pos.get('pnl_usd', 0),
                'days_held': pos.get('days_held', 0),
                'shares': pos.get('shares', 0),
                'exit_signal': exit_signal,
                # v3.3: Sector regime info
                'sector': pos.get('sector', 'Unknown'),
                'sector_regime': pos.get('sector_regime', 'UNKNOWN'),
                'sector_regime_adjustment': pos.get('sector_regime_adjustment', 0),
                'sector_confidence_threshold': pos.get('sector_confidence_threshold', 65)
            })

        # v3.3: Get sector regime summary (convert DataFrame to list of dicts)
        sector_regime_summary = updates.get('sector_regime_summary')
        if sector_regime_summary is not None:
            # Convert DataFrame to list of dictionaries for JSON serialization
            # Use make_json_serializable to handle NaN values properly
            sector_regime_summary = make_json_serializable(sector_regime_summary)

        # Clean all data to ensure JSON serializability (handles NaN, inf, etc.)
        response_data = make_json_serializable({
            'regime': regime_info,
            'stats': stats,
            'positions': positions_with_signals,
            'sector_regime_summary': sector_regime_summary,  # v3.3
            'last_updated': datetime.now().isoformat()
        })

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Portfolio status API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/add', methods=['POST'])
def api_portfolio_add():
    """Add a new position to portfolio"""
    try:
        from portfolio_manager_v3 import PortfolioManagerV3

        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        entry_price = data.get('entry_price')
        entry_date = data.get('entry_date')
        filters = data.get('filters', {})
        amount = data.get('amount', 1000)

        if not symbol or not entry_price or not entry_date:
            return jsonify({'error': 'Missing required fields'}), 400

        # Initialize portfolio manager v3
        pm = PortfolioManagerV3()

        # Add position
        success = pm.add_position(
            symbol=symbol,
            entry_price=float(entry_price),
            entry_date=entry_date,
            filters=filters,
            amount=float(amount)
        )

        if not success:
            return jsonify({'error': 'Failed to add position (may already exist or portfolio full)'}), 400

        # Get position with Smart Exit levels
        positions = pm.get_active_positions()
        position = next((p for p in positions if p.get('symbol') == symbol), None)
        position_data = None
        if position:
            position_data = {
                'symbol': symbol,
                'entry_price': position.get('entry_price'),
                'sl_price': position.get('sl_price'),
                'tp1_price': position.get('tp1_price'),
                'tp2_price': position.get('tp2_price'),
            }

        return jsonify({
            'success': True,
            'symbol': symbol,
            'entry_price': entry_price,
            'entry_date': entry_date,
            'amount': amount,
            'position': position_data,
            'message': f'✅ Added {symbol} to portfolio'
        })

    except Exception as e:
        logger.error(f"Add position API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/close', methods=['POST'])
def api_portfolio_close():
    """Close a position"""
    try:
        from portfolio_manager_v3 import PortfolioManagerV3
        from datetime import datetime
        import yfinance as yf

        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        exit_date = data.get('exit_date', datetime.now().strftime('%Y-%m-%d'))

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        # Initialize portfolio manager v3
        pm = PortfolioManagerV3()

        # Get current price
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='1d')
        if hist.empty:
            return jsonify({'error': 'Could not fetch current price'}), 400

        current_price = float(hist['Close'].iloc[-1])

        # Close position
        closed_pos = pm.close_position(
            symbol=symbol,
            exit_price=current_price,
            exit_date=exit_date,
            exit_reason='MANUAL_EXIT'
        )

        if not closed_pos:
            return jsonify({'error': f'{symbol} not found in active positions'}), 404

        return jsonify({
            'success': True,
            'symbol': symbol,
            'exit_price': closed_pos['exit_price'],
            'return_pct': closed_pos['return_pct'],
            'return_usd': closed_pos['return_usd'],
            'exit_reason': closed_pos['exit_reason'],
            'days_held': closed_pos['days_held']
        })

    except Exception as e:
        logger.error(f"Close position API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/history', methods=['GET'])
def api_portfolio_history():
    """Get trade history and performance stats"""
    try:
        from portfolio_manager_v3 import PortfolioManagerV3

        pm = PortfolioManagerV3()
        closed_trades = pm.get_closed_trades()
        stats = pm.portfolio.get('stats', {})

        # Calculate additional insights
        if closed_trades:
            returns = [t['return_pct'] for t in closed_trades]
            winners = [r for r in returns if r > 0]
            losers = [r for r in returns if r <= 0]

            # Exit reason breakdown
            exit_reasons = {}
            for t in closed_trades:
                reason = t.get('exit_reason', 'UNKNOWN')
                if reason not in exit_reasons:
                    exit_reasons[reason] = {'count': 0, 'total_return': 0}
                exit_reasons[reason]['count'] += 1
                exit_reasons[reason]['total_return'] += t.get('return_pct', 0)

            # Calculate avg return per reason
            for reason in exit_reasons:
                count = exit_reasons[reason]['count']
                exit_reasons[reason]['avg_return'] = exit_reasons[reason]['total_return'] / count if count > 0 else 0

            insights = {
                'total_trades': len(closed_trades),
                'winners': len(winners),
                'losers': len(losers),
                'win_rate': (len(winners) / len(closed_trades) * 100) if closed_trades else 0,
                'avg_winner': sum(winners) / len(winners) if winners else 0,
                'avg_loser': sum(losers) / len(losers) if losers else 0,
                'largest_win': max(returns) if returns else 0,
                'largest_loss': min(returns) if returns else 0,
                'avg_holding_days': sum(t.get('days_held', 0) for t in closed_trades) / len(closed_trades) if closed_trades else 0,
                'total_pnl': sum(t.get('return_usd', 0) for t in closed_trades),
                'exit_reasons': exit_reasons
            }
        else:
            insights = {
                'total_trades': 0,
                'winners': 0,
                'losers': 0,
                'win_rate': 0,
                'avg_winner': 0,
                'avg_loser': 0,
                'largest_win': 0,
                'largest_loss': 0,
                'avg_holding_days': 0,
                'total_pnl': 0,
                'exit_reasons': {}
            }

        # Sort trades by exit date (newest first)
        sorted_trades = sorted(closed_trades, key=lambda x: x.get('exit_date', ''), reverse=True)

        return jsonify({
            'trades': sorted_trades,
            'insights': insights,
            'stats': stats
        })

    except Exception as e:
        logger.error(f"Portfolio history API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/remove', methods=['POST'])
def api_portfolio_remove():
    """Remove a position without closing it (delete only)"""
    try:
        from portfolio_manager_v3 import PortfolioManagerV3

        data = request.get_json()
        symbol = data.get('symbol', '').upper()

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        # Initialize portfolio manager v3
        pm = PortfolioManagerV3()

        # Remove position
        success = pm.remove_position(symbol=symbol)

        if not success:
            return jsonify({'error': f'{symbol} not found in active positions'}), 404

        # Also remove from drafts if exists
        drafts_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'draft_stocks.json')
        if os.path.exists(drafts_file):
            try:
                with open(drafts_file, 'r') as f:
                    drafts_data = json.load(f)

                # Remove the symbol from drafts
                original_count = len(drafts_data.get('drafts', []))
                drafts_data['drafts'] = [d for d in drafts_data.get('drafts', []) if d['symbol'] != symbol]
                drafts_data['count'] = len(drafts_data['drafts'])

                if len(drafts_data['drafts']) < original_count:
                    with open(drafts_file, 'w') as f:
                        json.dump(drafts_data, f, indent=2)
                    logger.info(f"Also removed {symbol} from drafts")
            except Exception as e:
                logger.warning(f"Could not remove from drafts: {e}")

        return jsonify({
            'success': True,
            'symbol': symbol,
            'message': f'{symbol} removed from portfolio and drafts'
        })

    except Exception as e:
        logger.error(f"Remove position API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/pullback-catalyst-screen', methods=['POST'])
def api_pullback_catalyst_screen():
    """API endpoint for Pullback Catalyst screening"""
    try:
        data = request.get_json()

        # Extract criteria
        min_price = data.get('min_price', 20.0)
        max_price = data.get('max_price', 500.0)
        min_volume_ratio = data.get('min_volume_ratio', 1.8)
        min_catalyst_score = data.get('min_catalyst_score', 45.0)
        max_rsi = data.get('max_rsi', 76.0)
        max_stocks = data.get('max_stocks', 20)
        lookback_days = data.get('lookback_days', 5)

        logger.info(f"🎯 Starting Pullback Catalyst screening")
        logger.info(f"   Filters: Price ${min_price}-${max_price}, Vol Ratio >= {min_volume_ratio}x")
        logger.info(f"   Catalyst Score >= {min_catalyst_score}, RSI <= {max_rsi}")

        # Run pullback catalyst screening
        opportunities = pullback_catalyst_screener.screen_pullback_opportunities(
            min_price=min_price,
            max_price=max_price,
            min_volume_ratio=min_volume_ratio,
            min_catalyst_score=min_catalyst_score,
            max_rsi=max_rsi,
            max_stocks=max_stocks,
            lookback_days=lookback_days,
        )

        # Enrich with ETF information
        opportunities_with_etf = enrich_with_etf_info(opportunities)

        # Clean results for JSON serialization
        cleaned_opportunities = clean_analysis_results(opportunities_with_etf)

        return jsonify({
            'opportunities': cleaned_opportunities,
            'found_opportunities': len(opportunities),
            'criteria': {
                'min_price': min_price,
                'max_price': max_price,
                'min_volume_ratio': min_volume_ratio,
                'min_catalyst_score': min_catalyst_score,
                'max_rsi': max_rsi,
                'lookback_days': lookback_days,
            }
        })

    except Exception as e:
        logger.error(f"Pullback catalyst screening API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/monthly-performance', methods=['GET'])
def api_portfolio_monthly_performance():
    """API endpoint for monthly performance breakdown"""
    try:
        from portfolio_manager_v3 import PortfolioManagerV3
        from collections import defaultdict

        pm = PortfolioManagerV3()
        history = pm.get_trade_history()

        # Group by month
        monthly_data = defaultdict(lambda: {
            'pnl': 0,
            'trades': 0,
            'wins': 0,
            'gross_profit': 0,
            'gross_loss': 0,
        })

        for trade in history:
            exit_date = trade.get('exit_date', '')
            if not exit_date:
                continue

            month = exit_date[:7]  # YYYY-MM
            pnl = trade.get('pnl', 0)

            monthly_data[month]['trades'] += 1
            monthly_data[month]['pnl'] += pnl

            if pnl > 0:
                monthly_data[month]['wins'] += 1
                monthly_data[month]['gross_profit'] += pnl
            else:
                monthly_data[month]['gross_loss'] += abs(pnl)

        # Convert to list and calculate metrics
        monthly_performance = []
        for month in sorted(monthly_data.keys()):
            data = monthly_data[month]
            win_rate = (data['wins'] / data['trades'] * 100) if data['trades'] > 0 else 0
            profit_factor = (data['gross_profit'] / data['gross_loss']) if data['gross_loss'] > 0 else float('inf')

            monthly_performance.append({
                'month': month,
                'pnl': data['pnl'],
                'trades': data['trades'],
                'wins': data['wins'],
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'gross_profit': data['gross_profit'],
                'gross_loss': data['gross_loss'],
            })

        # Calculate summary stats
        if monthly_performance:
            pnls = [m['pnl'] for m in monthly_performance]
            avg_monthly = sum(pnls) / len(pnls)
            positive_months = sum(1 for p in pnls if p > 0)
            total_pnl = sum(pnls)
        else:
            avg_monthly = 0
            positive_months = 0
            total_pnl = 0

        return jsonify({
            'monthly_performance': monthly_performance,
            'summary': {
                'total_months': len(monthly_performance),
                'positive_months': positive_months,
                'positive_months_pct': (positive_months / len(monthly_performance) * 100) if monthly_performance else 0,
                'avg_monthly_pnl': avg_monthly,
                'total_pnl': total_pnl,
                'best_month': max(pnls) if pnls else 0,
                'worst_month': min(pnls) if pnls else 0,
            }
        })

    except Exception as e:
        logger.error(f"Monthly performance API error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


# =====================================================
# LOCAL LLM API ENDPOINTS
# =====================================================

# Initialize LLM (lazy loading)
_llm_analyzer = None
_llm_integration = None


def get_llm_analyzer():
    """Get or initialize LLM analyzer (lazy loading)"""
    global _llm_analyzer
    if _llm_analyzer is None:
        try:
            from local_llm import StockAnalyzerLLM
            _llm_analyzer = StockAnalyzerLLM()
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            _llm_analyzer = False
    return _llm_analyzer if _llm_analyzer else None


def get_llm_integration():
    """Get or initialize LLM screener integration (lazy loading)"""
    global _llm_integration
    if _llm_integration is None:
        try:
            from local_llm.screener_integration import LLMScreenerIntegration
            _llm_integration = LLMScreenerIntegration()
        except Exception as e:
            logger.error(f"Failed to initialize LLM integration: {e}")
            _llm_integration = False
    return _llm_integration if _llm_integration else None


@app.route('/api/llm/status', methods=['GET'])
def api_llm_status():
    """Check LLM availability and status"""
    try:
        analyzer = get_llm_analyzer()

        if analyzer is None:
            return jsonify({
                'available': False,
                'error': 'LLM not initialized',
                'setup_instructions': [
                    '1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh',
                    '2. Start Ollama: ollama serve',
                    '3. Pull model: ollama pull llama3.2:3b'
                ]
            })

        if not analyzer.is_available():
            return jsonify({
                'available': False,
                'error': 'Ollama not running',
                'setup_instructions': [
                    '1. Start Ollama: ollama serve',
                    '2. Check if running: curl http://localhost:11434/api/tags'
                ]
            })

        # Get available models
        models = analyzer.client.get_available_models()

        return jsonify({
            'available': True,
            'model': analyzer.model,
            'available_models': models,
            'recommended_models': {
                'fast': 'llama3.2:1b',
                'balanced': 'llama3.2:3b',
                'quality': 'mistral:7b'
            }
        })

    except Exception as e:
        logger.error(f"LLM status error: {e}")
        return jsonify({'error': str(e), 'available': False}), 500


@app.route('/api/llm/analyze', methods=['POST'])
def api_llm_analyze():
    """Analyze a stock using Local LLM"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        analyzer = get_llm_analyzer()

        if analyzer is None or not analyzer.is_available():
            return jsonify({
                'error': 'LLM not available',
                'available': False
            }), 503

        # Get stock data
        import yfinance as yf
        import numpy as np

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="90d")

        if hist.empty:
            return jsonify({'error': f'No data for {symbol}'}), 400

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
        rsi = float(100 - (100 / (1 + rs.iloc[-1]))) if not np.isnan(rs.iloc[-1]) else 50

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

        # Get sector info
        info = ticker.info
        sector = info.get('sector', 'Unknown')

        # Run LLM analysis
        result = analyzer.analyze_stock(
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
            market_regime=data.get('market_regime', 'NEUTRAL'),
            sector=sector,
            sector_regime=data.get('sector_regime', 'NEUTRAL'),
            additional_context=data.get('context', '')
        )

        if result is None:
            return jsonify({'error': 'Analysis failed'}), 500

        return jsonify({
            'symbol': result.symbol,
            'recommendation': result.recommendation,
            'confidence': result.confidence,
            'entry_price': result.entry_price,
            'stop_loss': result.stop_loss,
            'take_profit': result.take_profit,
            'risk_level': result.risk_level,
            'reasoning': result.reasoning,
            'key_factors': result.key_factors,
            'warnings': result.warnings,
            'analysis_time': result.analysis_time,
            'current_price': current_price,
            'indicators': {
                'rsi': rsi,
                'atr': atr,
                'sma20': sma20,
                'sma50': sma50,
                'support': support,
                'resistance': resistance,
                'volume_ratio': volume_ratio,
                'trend': trend
            }
        })

    except Exception as e:
        logger.error(f"LLM analyze error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/second-opinion', methods=['POST'])
def api_llm_second_opinion():
    """Get LLM second opinion on a trade"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        entry = data.get('entry_price')
        stop_loss = data.get('stop_loss')
        take_profit = data.get('take_profit')
        action = data.get('action', 'BUY')

        if not symbol or not entry:
            return jsonify({'error': 'Symbol and entry_price required'}), 400

        analyzer = get_llm_analyzer()

        if analyzer is None or not analyzer.is_available():
            return jsonify({
                'error': 'LLM not available',
                'available': False,
                'proceed': True,
                'message': 'LLM unavailable - proceeding without opinion'
            })

        analysis = {
            'price': entry,
            'entry': entry,
            'stop_loss': stop_loss or entry * 0.95,
            'take_profit': take_profit or entry * 1.10,
        }

        result = analyzer.get_second_opinion(
            symbol=symbol,
            current_analysis=analysis,
            proposed_action=action
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"LLM second opinion error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/filter-candidates', methods=['POST'])
def api_llm_filter_candidates():
    """Filter screener candidates using LLM"""
    try:
        data = request.get_json()
        candidates = data.get('candidates', [])
        max_analyze = data.get('max_analyze', 10)

        if not candidates:
            return jsonify({'error': 'No candidates provided'}), 400

        integration = get_llm_integration()

        if integration is None or not integration.available:
            return jsonify({
                'error': 'LLM not available',
                'available': False,
                'candidates': candidates  # Return unfiltered
            })

        filtered = integration.filter_candidates(candidates, max_analyze=max_analyze)

        return jsonify({
            'available': True,
            'original_count': len(candidates),
            'filtered_count': len(filtered),
            'candidates': filtered
        })

    except Exception as e:
        logger.error(f"LLM filter error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/llm/news-sentiment', methods=['POST'])
def api_llm_news_sentiment():
    """Analyze news sentiment using LLM"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        headlines = data.get('headlines', [])

        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400

        analyzer = get_llm_analyzer()

        if analyzer is None or not analyzer.is_available():
            return jsonify({
                'error': 'LLM not available',
                'available': False
            })

        result = analyzer.analyze_news_sentiment(symbol, headlines)

        return jsonify(result)

    except Exception as e:
        logger.error(f"LLM news sentiment error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# RAPID TRADER - Target 5-15%/month
# ============================================================

@app.route('/rapid')
def rapid_trader_page():
    """Rapid Trader page - quick trades, fast rotation"""
    return render_template('rapid_trader.html')


@app.route('/api/rapid/signals')
def api_rapid_signals():
    """Get rapid rotation buy signals"""
    try:
        from screeners.rapid_rotation_screener import RapidRotationScreener

        screener = RapidRotationScreener()
        screener.load_data()
        signals = screener.screen(top_n=10)

        # Convert to dict (v3.0 - includes sector, regime, alt data)
        signals_data = []
        for s in signals:
            signals_data.append({
                'symbol': s.symbol,
                'score': s.score,
                'entry_price': s.entry_price,
                'stop_loss': s.stop_loss,
                'take_profit': s.take_profit,
                'risk_reward': s.risk_reward,
                'max_loss': s.max_loss,
                'expected_gain': s.expected_gain,
                'rsi': s.rsi,
                'atr_pct': s.atr_pct,
                'momentum_5d': s.momentum_5d,
                'momentum_20d': s.momentum_20d,
                'distance_from_high': s.distance_from_high,
                'reasons': s.reasons,
                # v3.0 fields
                'sector': getattr(s, 'sector', ''),
                'market_regime': getattr(s, 'market_regime', ''),
                'sector_score': getattr(s, 'sector_score', 0),
                'alt_data_score': getattr(s, 'alt_data_score', 0),
            })

        return jsonify({
            'count': len(signals_data),
            'signals': signals_data,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Rapid signals error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/portfolio')
def api_rapid_portfolio():
    """Get rapid portfolio status with alerts"""
    try:
        from rapid_portfolio_manager import RapidPortfolioManager

        pm = RapidPortfolioManager()
        statuses = pm.check_all_positions()
        summary = pm.get_portfolio_summary()

        # Convert to dict
        statuses_data = []
        for s in statuses:
            statuses_data.append({
                'symbol': s.symbol,
                'entry_price': s.entry_price,
                'current_price': s.current_price,
                'pnl_pct': s.pnl_pct,
                'pnl_usd': s.pnl_usd,
                'days_held': s.days_held,
                'signal': s.signal.value,
                'reasons': s.reasons,
                'action': s.action,
                'new_candidates': s.new_candidates
            })

        return jsonify({
            'summary': summary,
            'statuses': statuses_data,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Rapid portfolio error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/position', methods=['POST'])
def api_rapid_add_position():
    """Add position to rapid portfolio"""
    try:
        from rapid_portfolio_manager import RapidPortfolioManager

        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        shares = data.get('shares')
        entry_price = data.get('entry_price')
        stop_loss = data.get('stop_loss')
        take_profit = data.get('take_profit')

        if not all([symbol, shares, entry_price, stop_loss, take_profit]):
            return jsonify({'error': 'Missing required fields'}), 400

        pm = RapidPortfolioManager()
        pm.add_position(
            symbol=symbol,
            shares=int(shares),
            entry_price=float(entry_price),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit)
        )

        return jsonify({
            'success': True,
            'message': f'Added {symbol} to portfolio'
        })

    except Exception as e:
        logger.error(f"Add rapid position error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/position/<symbol>', methods=['DELETE'])
def api_rapid_remove_position(symbol):
    """Remove position from rapid portfolio"""
    try:
        from rapid_portfolio_manager import RapidPortfolioManager

        pm = RapidPortfolioManager()
        pos = pm.remove_position(symbol.upper())

        if pos:
            return jsonify({
                'success': True,
                'message': f'Removed {symbol} from portfolio'
            })
        else:
            return jsonify({'error': f'{symbol} not found'}), 404

    except Exception as e:
        logger.error(f"Remove rapid position error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)