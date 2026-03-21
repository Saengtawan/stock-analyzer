"""
Flask Web Application for Stock Analyzer
v4.0: Added WebSocket support for real-time updates
"""
# v6.51: eventlet monkey-patch MUST be first before any other imports
# Fixes "AssertionError: write() before start_response" on WebSocket upgrade
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from functools import wraps
import json
import sys
import os
import threading
import time
import secrets
import hmac
from datetime import datetime, timedelta
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

# v6.41: Version fetched from backend engine (single source of truth)
APP_VERSION = '...'  # Placeholder - actual version loaded from engine via API

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True  # v5.3: Disable template caching
CORS(app)

# v4.0: WebSocket for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# v4.9: API authentication for dangerous endpoints
# Set RAPID_API_SECRET in environment, or a random key is generated per session
_API_SECRET = os.environ.get('RAPID_API_SECRET', '')
if not _API_SECRET:
    _API_SECRET = secrets.token_hex(32)
    logger.debug(f"No RAPID_API_SECRET set — generated ephemeral key (set env var for persistence)")


def require_api_auth(f):
    """Decorator: require X-API-Key header matching RAPID_API_SECRET."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-API-Key', '')
        if not token or not hmac.compare_digest(token, _API_SECRET):
            return jsonify({'error': 'Unauthorized — set X-API-Key header'}), 401
        return f(*args, **kwargs)
    return decorated

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

# Note: Signals API does not use caching - user wants fresh data
# Timeout is handled on client side (30 minutes)


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

@app.route('/health')
def health_check():
    """
    Health check endpoint for monitoring (v6.21 Production Grade)

    Returns JSON with system health status.
    Used by monitoring tools, load balancers, and health dashboards.

    Example response:
    {
        "status": "healthy",
        "timestamp": "2026-02-13T10:30:00",
        "components": {
            "app": "ok",
            "data_manager": "ok",
            "vix_fetch": "ok"
        },
        "vix_current": 18.5
    }
    """
    import time
    from datetime import datetime as dt

    health = {
        "status": "healthy",
        "timestamp": dt.now().isoformat(),
        "components": {},
        "vix_current": None
    }

    # Check 1: Flask app (if we got here, it's ok)
    health["components"]["app"] = "ok"

    # Check 2: Data manager availability
    try:
        if analyzer and analyzer.data_manager:
            health["components"]["data_manager"] = "ok"
        else:
            health["components"]["data_manager"] = "unavailable"
            health["status"] = "degraded"
    except Exception as e:
        health["components"]["data_manager"] = f"error: {str(e)}"
        health["status"] = "unhealthy"

    # Check 3: VIX fetch (critical for VIX Adaptive Strategy)
    try:
        import yfinance as yf
        vix_ticker = yf.Ticker('^VIX')
        vix_data = vix_ticker.history(period='1d')
        if not vix_data.empty:
            vix = float(vix_data['Close'].iloc[-1])
            # Data quality check
            if 0 <= vix <= 100:
                health["components"]["vix_fetch"] = "ok"
                health["vix_current"] = round(vix, 2)
            else:
                health["components"]["vix_fetch"] = f"invalid_range: {vix}"
                health["status"] = "degraded"
        else:
            health["components"]["vix_fetch"] = "no_data"
            health["status"] = "degraded"
    except Exception as e:
        health["components"]["vix_fetch"] = f"error: {str(e)}"
        health["status"] = "degraded"

    # Return appropriate HTTP status code
    status_code = 200 if health["status"] == "healthy" else 503

    return jsonify(health), status_code

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
        except (AttributeError, TypeError, ValueError):
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
# RAPID TRADER v4.0 - Smart Regime Edition
# Target: +5.5%/mo, DD 8.9%, WR 49%
# ============================================================

@app.route('/rapid')
def rapid_trader_page():
    """
    Rapid Trader page - quick trades, fast rotation

    v6.11: Single Source of Truth - sessions from config/trading.yaml
    """
    # Load sessions from config (Single Source of Truth)
    from config.strategy_config import RapidRotationConfig
    import os

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'config', 'trading.yaml'
    )  # v6.80: Fixed path — app.py is src/web/app.py → need 3× dirname to reach project root

    try:
        config = RapidRotationConfig.from_yaml(config_path)
        sessions_cfg = config.sessions

        # Build sessions list for frontend (v6.54: Added PED session)
        sessions = []
        for key in ['gapscan', 'morning', 'pem', 'ped', 'skip', 'midday', 'afternoon', 'ovn', 'preclose']:
            if hasattr(sessions_cfg, key):
                s = getattr(sessions_cfg, key)
                sessions.append({
                    'name': key,
                    'label': s.label if hasattr(s, 'label') else key.capitalize(),
                    'start': s.start if hasattr(s, 'start') else 0,
                    'end': s.end if hasattr(s, 'end') else 0,
                    'interval': s.interval if hasattr(s, 'interval') else 5,
                })

        # Fallback if no sessions found (v6.54: 9 sessions with PEM, PED, SKIP, OVN)
        if not sessions:
            sessions = [
                {'name': 'gapscan', 'label': 'Gap Scan', 'start': 360, 'end': 572, 'interval': -1},
                {'name': 'morning', 'label': 'Morning', 'start': 572, 'end': 600, 'interval': 3},
                {'name': 'pem', 'label': 'PEM', 'start': 572, 'end': 615, 'interval': -1},
                {'name': 'ped', 'label': 'PED', 'start': 572, 'end': 630, 'interval': -1},
                {'name': 'skip', 'label': 'SKIP', 'start': 600, 'end': 605, 'interval': -1},
                {'name': 'midday', 'label': 'Midday', 'start': 605, 'end': 840, 'interval': 5},
                {'name': 'afternoon', 'label': 'Afternoon', 'start': 840, 'end': 945, 'interval': 5},
                {'name': 'ovn', 'label': 'OVN', 'start': 945, 'end': 950, 'interval': -1},
                {'name': 'preclose', 'label': 'Pre-Close', 'start': 950, 'end': 960, 'interval': 0},
            ]
    except Exception as e:
        logger.warning(f"Failed to load sessions from config: {e}")
        # Fallback sessions (v6.54: 9 sessions with PEM, PED, SKIP, OVN)
        sessions = [
            {'name': 'gapscan', 'label': 'Gap Scan', 'start': 360, 'end': 572, 'interval': -1},
            {'name': 'morning', 'label': 'Morning', 'start': 572, 'end': 600, 'interval': 3},
            {'name': 'pem', 'label': 'PEM', 'start': 572, 'end': 615, 'interval': -1},
            {'name': 'ped', 'label': 'PED', 'start': 572, 'end': 630, 'interval': -1},
            {'name': 'skip', 'label': 'SKIP', 'start': 600, 'end': 605, 'interval': -1},
            {'name': 'midday', 'label': 'Midday', 'start': 605, 'end': 840, 'interval': 5},
            {'name': 'afternoon', 'label': 'Afternoon', 'start': 840, 'end': 945, 'interval': 5},
            {'name': 'ovn', 'label': 'OVN', 'start': 945, 'end': 950, 'interval': -1},
            {'name': 'preclose', 'label': 'Pre-Close', 'start': 950, 'end': 960, 'interval': 0},
        ]

    return render_template('rapid_trader.html', default_sessions=sessions, app_version=APP_VERSION, api_key=_API_SECRET)


@app.route('/api/health/legacy')
def api_health_legacy():
    """System health check endpoint (legacy - checks Alpaca API)"""
    try:
        checks = {}
        issues = []

        # 1. Alpaca API (using broker abstraction layer)
        broker = None
        try:
            from engine.brokers import AlpacaBroker
            broker = AlpacaBroker(paper=True)
            account = broker.get_account()
            checks['alpaca_api'] = {
                'ok': True,
                'detail': f"Connected, ${account.portfolio_value:,.0f}"
            }
        except Exception as e:
            checks['alpaca_api'] = {'ok': False, 'detail': str(e)}
            issues.append(f"Alpaca API: {e}")

        # 2. Market clock
        try:
            if broker:
                clock = broker.get_clock()
                market_status = "Open" if clock.is_open else "Closed"
                checks['market_clock'] = {'ok': True, 'detail': market_status}
            else:
                checks['market_clock'] = {'ok': False, 'detail': 'Broker not available'}
        except Exception as e:
            checks['market_clock'] = {'ok': False, 'detail': str(e)}
            issues.append(f"Market clock: {e}")

        # 3. Portfolio data - v6.74: Use DB as source of truth (engine.positions is empty in webapp auto_start=False)
        try:
            engine = get_auto_trading_engine()
            # v6.74: Use PositionRepository instead of engine.positions (always {} in webapp)
            from database.repositories.position_repository import PositionRepository
            try:
                db_pos = PositionRepository().get_all(use_cache=False)
                memory_count = len(db_pos) if db_pos else 0
            except Exception:
                memory_count = 0
            alpaca_positions = broker.get_positions() if broker else []

            alpaca_count = len(alpaca_positions)

            if memory_count != alpaca_count:
                checks['positions_sync'] = {
                    'ok': False,
                    'detail': f"Mismatch: tracked={memory_count}, Alpaca={alpaca_count}"
                }
                issues.append(f"Position mismatch: tracked={memory_count}, Alpaca={alpaca_count}")
            else:
                checks['positions_sync'] = {
                    'ok': True,
                    'detail': f"{alpaca_count} position(s), in sync"
                }
        except Exception as e:
            checks['positions_sync'] = {'ok': False, 'detail': str(e)}
            issues.append(f"Position sync: {e}")

        # 4. Web server (obviously OK if we're responding)
        checks['web_server'] = {'ok': True, 'detail': 'Responding'}

        return jsonify({
            'healthy': len(issues) == 0,
            'timestamp': datetime.now().isoformat(),
            'checks': checks,
            'issues': issues
        })

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'healthy': False,
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'issues': [str(e)]
        }), 500


@app.route('/api/rapid/spy-regime')
def api_rapid_spy_regime():
    """
    v4.9.5: Get SPY regime from ENGINE (4-criteria: SMA20 + RSI + Ret5d + VIX).
    Falls back to screener only if engine unavailable.
    """
    try:
        # v4.9.5: Use engine's regime (Single Source of Truth)
        engine = get_auto_trading_engine()
        if engine:
            status = engine.get_status()
            regime_details = status.get('regime_details') or {}
            response = {
                'is_bull': status.get('market_regime') in ('BULL',),
                'reason': status.get('regime_detail', ''),
                'details': regime_details,
                'source': 'engine',
                'timestamp': datetime.now().isoformat()
            }
            # Convert numpy types to native Python types
            response = convert_numpy_types(response)
            return jsonify(response)

        # v6.20 FIX: Lightweight fallback (no full screener initialization!)
        import yfinance as yf
        spy = yf.Ticker('SPY')
        hist = spy.history(period='1mo')
        if len(hist) >= 20:
            sma20 = hist['Close'].rolling(20).mean().iloc[-1]
            current = hist['Close'].iloc[-1]
            is_bull = current > sma20
            pct_diff = ((current - sma20) / sma20) * 100
            response = {
                'is_bull': is_bull,
                'reason': f"SPY ${current:.2f} {'>' if is_bull else '<'} SMA20 ${sma20:.2f} ({pct_diff:+.1f}%)",
                'details': {'spy': float(current), 'sma20': float(sma20)},
                'source': 'lightweight_fallback',
                'timestamp': datetime.now().isoformat()
            }
        else:
            response = {
                'is_bull': True,
                'reason': 'Insufficient data (default BULL)',
                'details': {},
                'source': 'default_fallback',
                'timestamp': datetime.now().isoformat()
            }
        # Convert numpy types to native Python types
        response = convert_numpy_types(response)
        return jsonify(response)

    except Exception as e:
        logger.error(f"SPY regime check error: {e}")
        return jsonify({'error': str(e), 'is_bull': True, 'source': 'error_fallback'}), 500


@app.route('/api/engine/config')
def api_engine_config():
    """v4.9.5: Return ALL engine config params for UI Single Source of Truth."""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not initialized'}), 503
        return jsonify(engine.get_full_config())
    except Exception as e:
        logger.error(f"Engine config error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/sector-regimes')
def api_sector_regimes():
    """Sector regime data for UI sector strip."""
    engine = get_auto_trading_engine()
    if not engine:
        return jsonify({'error': 'Engine not running', 'sectors': []})
    try:
        sectors = engine.get_sector_regimes()
        # Get allowed/blocked sectors based on market regime
        allowed_sectors = []
        blocked_sectors = []
        is_bull = engine.market_is_bull if hasattr(engine, 'market_is_bull') else True
        if not is_bull and hasattr(engine, '_get_bear_allowed_sectors'):
            allowed_sectors = engine._get_bear_allowed_sectors()
            # All other sectors are blocked in bear mode
            all_sectors = [s['sector'] for s in sectors]
            blocked_sectors = [s for s in all_sectors if s not in allowed_sectors]
        return jsonify({
            'sectors': sectors,
            'allowed_sectors': allowed_sectors,
            'blocked_sectors': blocked_sectors,
            'market_regime': 'BULL' if is_bull else 'BEAR'
        })
    except Exception as e:
        logger.error(f"Sector regimes error: {e}")
        return jsonify({'error': str(e), 'sectors': []})


@app.route('/api/rapid/scan-progress')
def api_scan_progress():
    """Get current scan progress for live UI display"""
    try:
        mgr = app.config.get('service_manager')
        if mgr and hasattr(mgr, '_scan_progress') and mgr._scan_progress:
            return jsonify(mgr._scan_progress)
        return jsonify({'phase': 'idle', 'message': 'No scan in progress'})
    except Exception as e:
        return jsonify({'phase': 'error', 'message': str(e)})


@app.route('/api/rapid/signals')
def api_rapid_signals():
    """Get rapid rotation buy signals from DB (primary) or cache (fallback)"""
    import json as _json

    # Phase 1B: Try database first
    try:
        from database.repositories import SignalRepository, ScanRepository

        sig_repo = SignalRepository()
        scan_repo = ScanRepository()

        # Get latest scan session
        latest_scan = scan_repo.get_latest()

        # v6.44: Get ALL active signals (not just from latest scan)
        # Reason: When continuous scan finds 0 signals, previous valid signals should still show
        # Filter: Only show signals from last 30 minutes (not old stale signals)
        # Deduplicate: Only keep latest signal per symbol (engine creates duplicates)
        from datetime import timedelta
        active_signals = sig_repo.get_active()
        waiting_signals = sig_repo.get_waiting()

        # Filter recent signals only (last 30 minutes)
        cutoff_time = datetime.now() - timedelta(minutes=30)
        active_signals = [s for s in active_signals if s.signal_time and s.signal_time >= cutoff_time]
        waiting_signals = [s for s in waiting_signals if s.signal_time and s.signal_time >= cutoff_time]

        # Deduplicate: Keep only the latest signal per symbol
        symbol_map = {}
        for sig in active_signals:
            if sig.symbol not in symbol_map or sig.signal_time > symbol_map[sig.symbol].signal_time:
                symbol_map[sig.symbol] = sig
        active_signals = list(symbol_map.values())

        symbol_map_waiting = {}
        for sig in waiting_signals:
            if sig.symbol not in symbol_map_waiting or sig.signal_time > symbol_map_waiting[sig.symbol].signal_time:
                symbol_map_waiting[sig.symbol] = sig
        waiting_signals = list(symbol_map_waiting.values())

        if latest_scan or active_signals or waiting_signals:
            # v6.84: Use real-time market status (not stale scan session value)
            # latest_scan.is_market_open reflects scan time (e.g. 07:51 ET = closed)
            # but market may have opened since then → show correct banner
            try:
                _engine = get_auto_trading_engine()
                _real_market_open = _engine.broker.is_market_open() if _engine else bool(latest_scan.is_market_open if latest_scan else False)
            except Exception:
                _real_market_open = bool(latest_scan.is_market_open if latest_scan else False)

            # Build response from DB (v6.44: convert all types to JSON-safe)
            data = {
                'mode': latest_scan.mode if (latest_scan and latest_scan.mode and _real_market_open) else ('closed' if not _real_market_open else 'market'),
                'is_market_open': int(_real_market_open),
                'timestamp': latest_scan.scan_time.isoformat() if latest_scan else datetime.now().isoformat(),
                'scan_time': latest_scan.scan_time_et if latest_scan else '',
                'session': latest_scan.session_type.title() if latest_scan else 'Unknown',
                'scan_type': latest_scan.session_type if latest_scan else 'unknown',
                'next_scan': latest_scan.next_scan_et if latest_scan else None,
                'next_scan_timestamp': latest_scan.next_scan_timestamp.isoformat() if latest_scan and latest_scan.next_scan_timestamp else None,
                'count': len(active_signals),
                'signals': [s.to_dict() for s in active_signals],
                'waiting_signals': [s.to_dict() for s in waiting_signals],
                'scan_duration_seconds': float(latest_scan.scan_duration_seconds) if latest_scan and latest_scan.scan_duration_seconds else 0.0,
                'regime': latest_scan.market_regime if latest_scan else 'UNKNOWN',
                'positions_status': {
                    'current': int(latest_scan.positions_current) if latest_scan and latest_scan.positions_current else 0,
                    'max': int(latest_scan.positions_max) if latest_scan and latest_scan.positions_max else 0,
                    'is_full': int(bool(latest_scan.positions_full)) if latest_scan and latest_scan.positions_full else 0
                },
                'pool_size': int(latest_scan.pool_size) if latest_scan and latest_scan.pool_size else 0,
                'source': 'database'  # For monitoring
            }

            # Calculate cache age
            if latest_scan:
                cache_ts = latest_scan.scan_time
                cache_age = (datetime.now() - cache_ts).total_seconds()
                data['cache_age_seconds'] = round(cache_age, 0)
                data['status'] = 'fresh' if cache_age < 1200 else 'stale'
            else:
                data['cache_age_seconds'] = 0
                data['status'] = 'fresh'

            # Phase 2: Add pre-filter status from database
            try:
                from database import PreFilterRepository
                pf_repo = PreFilterRepository()
                latest_pf = pf_repo.get_latest_session()

                if latest_pf:
                    data['prefilter_status'] = {
                        'pool_size': latest_pf.pool_size,
                        'last_updated': latest_pf.scan_time.isoformat() if latest_pf.scan_time else None,
                        'is_ready': latest_pf.is_ready,
                        'evening_status': latest_pf.status if latest_pf.scan_type == 'evening' else None,
                        'pre_open_status': latest_pf.status if latest_pf.scan_type == 'pre_open' else None,
                        'total_scanned': latest_pf.total_scanned,
                        'duration_seconds': latest_pf.duration_seconds,
                        'source': 'database'
                    }
                else:
                    data['prefilter_status'] = None
            except Exception as pf_err:
                logger.debug(f"Could not get pre-filter from DB: {pf_err}")
                data['prefilter_status'] = None

            logger.debug(f"📊 Signals from DB: {len(active_signals)} active, {len(waiting_signals)} waiting")
            return jsonify(data)

    except Exception as db_err:
        # Phase 1D: Database is single source of truth - no fallback
        logger.error(f"🚨 CRITICAL: Database read failed: {db_err}")

        # Alert: DB read failure
        try:
            from database.repositories import AlertsRepository, Alert
            alerts_repo = AlertsRepository()
            alerts_repo.create(Alert(
                alert_type='db_read_failure',
                severity='critical',
                message=f'Database read failed (no fallback available): {str(db_err)}',
                source='web_api'
            ))
        except Exception:
            pass  # Don't let alert failure break the request

        # Return error - no JSON fallback in Phase 1D
        return jsonify({
            'error': 'Database unavailable',
            'message': 'Unable to fetch signals from database. Please try again.',
            'source': 'error',
            'count': 0,
            'signals': []
        }), 503  # Service Unavailable


@app.route('/api/discovery/picks')
def api_discovery_picks():
    """Get Discovery Engine picks — display only, no execution."""
    try:
        from discovery.engine import get_discovery_engine
        engine = get_discovery_engine()
        picks = engine.get_picks()
        confidence = engine.get_confidence()
        return jsonify({
            'picks': picks,
            'count': len(picks),
            'last_scan': engine.get_last_scan(),
            'last_validation': engine.get_last_validation(),
            'last_intraday_scan': engine.get_last_intraday_scan(),
            'regime': engine.get_current_regime(),
            'confidence': confidence,
            # v6.0: Ensemble context (market-level, shared across all picks)
            'temporal_snapshot': engine._temporal_features or {},
            'sequence_prediction': engine._sequence_prediction or {},
            'leading_signals': engine._leading_signals or {},
            # v7.0: Council regime decision
            'regime_decision': engine._regime_decision or {},
        })
    except Exception as e:
        logger.error(f"Discovery API error: {e}")
        return jsonify({'picks': [], 'count': 0, 'last_scan': None, 'error': str(e)})


@app.route('/api/discovery/scan', methods=['POST'])
def api_discovery_scan():
    """Trigger a manual Discovery scan (runs in eventlet background task)."""
    try:
        from discovery.engine import get_discovery_engine
        engine = get_discovery_engine()

        # Check if scan already running
        progress = engine.get_scan_progress()
        if progress.get('status') in ('loading', 'scanning', 'scoring'):
            return jsonify({'status': 'already_running', 'progress': progress})

        def _run_scan():
            try:
                engine.run_scan()
            except Exception as e:
                logger.error(f"Discovery background scan error: {e}")
                engine._scan_progress = {'status': 'error', 'pct': 0, 'stage': str(e)}

        socketio.start_background_task(_run_scan)
        return jsonify({'status': 'started', 'message': 'Scan started in background. Poll /api/discovery/progress for status.'})
    except Exception as e:
        logger.error(f"Discovery scan error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/discovery/progress')
def api_discovery_progress():
    """Get Discovery scan progress."""
    try:
        from discovery.engine import get_discovery_engine
        return jsonify(get_discovery_engine().get_scan_progress())
    except Exception:
        return jsonify({})


@app.route('/api/discovery/stats')
def api_discovery_stats():
    """Get Discovery historical performance statistics."""
    try:
        from discovery.engine import get_discovery_engine
        return jsonify(get_discovery_engine().get_stats())
    except Exception as e:
        logger.error(f"Discovery stats error: {e}")
        return jsonify({'error': str(e)})


@app.route('/api/discovery/system')
def api_discovery_system():
    """v6.0: Full system status — health check for all components."""
    try:
        from discovery.engine import get_discovery_engine
        engine = get_discovery_engine()
        return jsonify({
            'version': '7.0',
            'components': {
                'kernel': {
                    'macro': {'fitted': engine.kernel is not None and engine.kernel.n_rows > 0,
                              'n_rows': getattr(engine.kernel, 'n_rows', 0) if engine.kernel else 0},
                    'stock': {'fitted': engine.stock_kernel is not None and getattr(engine.stock_kernel, '_fitted', False),
                              'n_rows': getattr(engine.stock_kernel, 'n_rows', 0) if engine.stock_kernel else 0},
                    'hold': {'fitted': engine._hold_data is not None},
                    'weekend': {'fitted': engine._weekend_data is not None},
                },
                'temporal': {'fitted': bool(engine._temporal_features),
                             'n_features': len(engine._temporal_features)},
                'sequence': {'fitted': engine._sequence_matcher._fitted,
                             'n_sequences': len(engine._sequence_matcher._historical or [])},
                'leading': {'fitted': engine._leading_indicators._historical_patterns is not None},
                'ensemble': {'weights': engine._ensemble.weights,
                             'v6_fitted': engine._v6_fitted},
                'calibrator': {'cached': engine._calibrator._cache is not None},
                'outcome_tracker': {'available': True},
                'regime_brain': engine._regime_brain.get_stats(),
                'stock_brain': engine._stock_brain.get_stats(),
                'risk_brain': engine._risk_brain.get_stats(),
            },
            'regime': engine.get_current_regime(),
            'last_scan': engine.get_last_scan(),
            'n_picks': len(engine._picks),
            'temporal_snapshot': engine._temporal_features or {},
            'sequence_prediction': engine._sequence_prediction or {},
            'leading_signals': engine._leading_signals or {},
        })
    except Exception as e:
        logger.error(f"Discovery system status error: {e}")
        return jsonify({'error': str(e)})


@app.route('/api/discovery/confidence')
def api_discovery_confidence():
    """Get Discovery self-calibration confidence and diagnostics."""
    try:
        from discovery.engine import get_discovery_engine
        engine = get_discovery_engine()
        return jsonify(engine.get_confidence())
    except Exception as e:
        logger.error(f"Discovery confidence error: {e}")
        return jsonify({'confidence': 50, 'error': str(e)})


@app.route('/api/discovery/learning')
def api_discovery_learning():
    """Get Discovery pattern learning analysis — feature IC, drift, interactions."""
    try:
        from discovery.pattern_learner import PatternLearner
        learner = PatternLearner()
        lookback = int(request.args.get('lookback', 90))

        ic_analysis = learner.analyze_feature_ic(lookback_days=lookback)
        interactions = learner.detect_interaction_effects(lookback_days=lookback)
        regime_ic = learner.compute_regime_ic_shift()

        return jsonify({
            'feature_ic': ic_analysis,
            'interactions': interactions[:5],  # top 5
            'regime_ic': regime_ic,
        })
    except Exception as e:
        logger.error(f"Discovery learning error: {e}")
        return jsonify({'error': str(e)})


@app.route('/api/discovery/outcomes')
def api_discovery_outcomes():
    """Get recent discovery outcomes for display."""
    try:
        import sqlite3
        from pathlib import Path
        db = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        limit = int(request.args.get('limit', 50))
        rows = conn.execute("""
            SELECT scan_date, symbol, predicted_er, actual_return_d3,
                   actual_return_d5, max_gain, max_dd, tp_hit, sl_hit,
                   regime, sector, atr_pct, vix_close
            FROM discovery_outcomes
            ORDER BY scan_date DESC, symbol
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()

        outcomes = [dict(r) for r in rows]
        return jsonify({'outcomes': outcomes, 'count': len(outcomes)})
    except Exception as e:
        logger.error(f"Discovery outcomes error: {e}")
        return jsonify({'outcomes': [], 'error': str(e)})


@app.route('/api/rapid/portfolio')
def api_rapid_portfolio():
    """Get rapid portfolio status with alerts — reads from engine positions"""
    try:
        statuses_data, summary = _build_positions_from_engine()
        pdt_info = get_pdt_info()

        # Include daily_stats and queue from engine
        # v7.8: Read daily_stats from cron_schedule.json (written by trading engine every cycle)
        # Webapp's own engine instance has stale date (set at webapp startup, never resets).
        from dataclasses import asdict
        engine = get_auto_trading_engine()
        daily_stats = None
        queue_data = []
        if engine:
            # Try cron_schedule.json first (written by actual trading engine, always fresh)
            try:
                import json as _json
                _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                _cron_file = os.path.join(_project_root, 'data', 'cron_schedule.json')
                if os.path.exists(_cron_file):
                    with open(_cron_file, 'r') as _f:
                        _cron = _json.load(_f)
                    daily_stats = _cron.get('daily_stats')
            except Exception:
                pass
            # Fallback to in-memory (stale but better than nothing)
            if daily_stats is None:
                ds = getattr(engine, 'daily_stats', None)
                daily_stats = asdict(ds) if ds else None
            # v6.93: Read queue from DB (SSoT) — webapp engine.signal_queue is stale
            # (loaded once at startup, never updated by trading loop)
            queue_data = []
            try:
                from database.repositories import QueueRepository
                db_queue = QueueRepository().get_all(status='waiting')
                for q in db_queue:
                    queued_at = q.queued_at or datetime.now()
                    age = (datetime.now() - queued_at).total_seconds() / 60
                    queue_data.append({
                        'symbol': q.symbol,
                        'signal_price': q.signal_price,
                        'score': q.score,
                        'age_minutes': round(age, 1),
                    })
            except Exception:
                # Fallback to in-memory queue
                for q in getattr(engine, 'signal_queue', []):
                    age = (datetime.now() - q.queued_at).total_seconds() / 60
                    queue_data.append({
                        'symbol': q.symbol,
                        'signal_price': q.signal_price,
                        'score': q.score,
                        'age_minutes': round(age, 1),
                    })

        return jsonify({
            'summary': summary,
            'statuses': statuses_data,
            'pdt': pdt_info,
            'daily_stats': daily_stats,
            'queue': queue_data,
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
        from engine.brokers import AlpacaBroker

        data = request.get_json()
        symbol = data.get('symbol', '').upper()
        shares = data.get('shares')
        entry_price = data.get('entry_price')
        stop_loss = data.get('stop_loss')
        take_profit = data.get('take_profit')

        if not all([symbol, shares, entry_price, stop_loss, take_profit]):
            return jsonify({'error': 'Missing required fields'}), 400

        # Initialize with broker for real-time data (v4.7)
        broker = AlpacaBroker(paper=True)
        pm = RapidPortfolioManager(broker=broker)
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
        from engine.brokers import AlpacaBroker

        # Initialize with broker for real-time data (v4.7)
        broker = AlpacaBroker(paper=True)

        # v7.5: Place market sell order on Alpaca before removing from tracking
        symbol_upper = symbol.upper()
        alpaca_pos = broker.get_position(symbol_upper)
        if alpaca_pos and int(float(alpaca_pos.qty)) > 0:
            qty = int(float(alpaca_pos.qty))
            logger.info(f"Selling {symbol_upper}: {qty} shares via rapid position remove")
            broker.place_market_sell(symbol_upper, qty)

        pm = RapidPortfolioManager(broker=broker)
        pos = pm.remove_position(symbol_upper)

        if pos:
            return jsonify({
                'success': True,
                'message': f'Sold and removed {symbol} from portfolio'
            })
        else:
            return jsonify({'error': f'{symbol} not found'}), 404

    except Exception as e:
        logger.error(f"Remove rapid position error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/performance')
def api_rapid_performance():
    """Get portfolio performance from Alpaca (v4.7)"""
    try:
        from rapid_portfolio_manager import RapidPortfolioManager

        period = request.args.get('period', '1M')

        # Try to use broker if available
        broker = None
        try:
            from engine.brokers import AlpacaBroker
            broker = AlpacaBroker(paper=True)
        except Exception as broker_err:
            logger.warning(f"Broker unavailable, using fallback: {broker_err}")

        # Create manager (with or without broker)
        manager = RapidPortfolioManager(broker=broker)

        # Get performance report
        report = manager.get_performance_report(period=period)

        return jsonify(report)

    except Exception as e:
        logger.error(f"Performance API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/trade-log')
def api_rapid_trade_log():
    """Get trade fills and slippage analysis (v4.7)"""
    try:
        days = int(request.args.get('days', 7))

        # Try to initialize broker
        try:
            from engine.brokers import AlpacaBroker
            broker = AlpacaBroker(paper=True)

            # Get fills and dividends separately (Alpaca API doesn't accept comma-separated)
            fills = broker.get_activities(activity_types='FILL', days=days)
            try:
                dividends = broker.get_activities(activity_types='DIV', days=days)
            except:
                dividends = []  # Dividends might not be available

            # Slippage analysis
            orders = broker.get_orders(status='filled')
            slippage = broker.analyze_slippage(fills, orders)

            return jsonify({
                'fills': fills,
                'dividends': dividends,
                'slippage': slippage,
                'period_days': days
            })

        except Exception as broker_err:
            logger.warning(f"Broker unavailable: {broker_err}")
            return jsonify({
                'error': 'Alpaca API keys not configured',
                'message': 'Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables',
                'fills': [],
                'dividends': [],
                'slippage': {},
                'period_days': days
            }), 503

    except Exception as e:
        logger.error(f"Trade log API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/calendar')
def api_rapid_calendar():
    """Get market calendar and holidays (v6.x - Uses market_calendar utility)"""
    try:
        from datetime import datetime, timedelta
        from utils.market_hours import MARKET_OPEN_STR, MARKET_CLOSE_STR

        days = int(request.args.get('days', 14))

        # US Market Holidays 2026 (definitive list)
        KNOWN_HOLIDAYS_2026 = {
            '2026-01-01',  # New Year's Day
            '2026-01-19',  # Martin Luther King Jr. Day
            '2026-02-16',  # Presidents Day
            '2026-04-03',  # Good Friday
            '2026-05-25',  # Memorial Day
            '2026-07-03',  # Independence Day (observed)
            '2026-09-07',  # Labor Day
            '2026-11-26',  # Thanksgiving
            '2026-12-25',  # Christmas
        }

        # Try to use broker
        try:
            from engine.brokers import AlpacaBroker
            broker = AlpacaBroker(paper=True)

            # Get calendar
            start_date = datetime.now().strftime('%Y-%m-%d')
            end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

            calendar = broker.get_calendar(start=start_date, end=end_date)
            holidays = broker.get_upcoming_holidays(days=days)
            is_open_tomorrow = broker.is_market_open_tomorrow()
            next_day = broker.get_next_market_day()

            # Build schedule using calendar data
            trading_days = {day['date'] for day in calendar}
            schedule = []

            current = datetime.now()
            for i in range(days):
                check_date = current + timedelta(days=i)
                date_str = check_date.strftime('%Y-%m-%d')
                day_name = check_date.strftime('%A')
                is_weekend = day_name in ['Saturday', 'Sunday']

                # Simplified logic: If in broker calendar = trading day, otherwise check weekend/holiday
                is_trading_day = date_str in trading_days

                # Holiday = weekday NOT in trading days AND (in known holidays OR not in calendar)
                is_holiday = (not is_weekend and not is_trading_day and
                             (date_str in KNOWN_HOLIDAYS_2026 or
                              (calendar and date_str >= min(trading_days) if trading_days else False)))

                if is_trading_day:
                    cal_entry = next((c for c in calendar if c['date'] == date_str), None)
                    schedule.append({
                        'date': date_str,
                        'day': day_name,
                        'is_open': True,
                        'open_time': cal_entry['open'] if cal_entry else MARKET_OPEN_STR,
                        'close_time': cal_entry['close'] if cal_entry else MARKET_CLOSE_STR,
                    })
                else:
                    schedule.append({
                        'date': date_str,
                        'day': day_name,
                        'is_open': False,
                        'is_weekend': is_weekend,
                        'is_holiday': is_holiday,
                    })

            return jsonify({
                'schedule': schedule,
                'holidays': holidays,
                'is_open_tomorrow': is_open_tomorrow,
                'next_trading_day': next_day,
                'period_days': days
            })

        except Exception as broker_err:
            logger.warning(f"Broker unavailable: {broker_err}")
            return jsonify({
                'error': 'Alpaca API keys not configured',
                'message': 'Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables',
                'schedule': [],
                'holidays': [],
                'is_open_tomorrow': None,
                'next_trading_day': None,
                'period_days': days
            }), 503

    except Exception as e:
        logger.error(f"Calendar API error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Alert Management APIs (Phase 4B)
# ============================================================================

@app.route('/api/rapid/alerts')
def api_rapid_alerts():
    """Get active alerts"""
    try:
        from database import AlertsRepository

        repo = AlertsRepository()
        alerts = repo.get_active(limit=100)

        return jsonify({
            'success': True,
            'count': len(alerts),
            'alerts': [alert.to_dict() for alert in alerts]
        })

    except Exception as e:
        logger.error(f"Alerts API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/alerts/all')
def api_rapid_alerts_all():
    """Get all alerts (active and resolved)"""
    try:
        from database import AlertsRepository

        repo = AlertsRepository()
        level = request.args.get('level', None)
        hours = int(request.args.get('hours', 24))
        limit = int(request.args.get('limit', 100))

        if level:
            alerts = repo.get_by_level(level, limit=limit)
        else:
            alerts = repo.get_recent(hours=hours, limit=limit)

        return jsonify({
            'success': True,
            'count': len(alerts),
            'alerts': [alert.to_dict() for alert in alerts]
        })

    except Exception as e:
        logger.error(f"Alerts API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/alerts/statistics')
def api_rapid_alerts_statistics():
    """Get alert statistics"""
    try:
        from database import AlertsRepository

        repo = AlertsRepository()
        hours = int(request.args.get('hours', 24))

        stats = repo.get_statistics(hours=hours)

        return jsonify({
            'success': True,
            'statistics': stats
        })

    except Exception as e:
        logger.error(f"Alerts statistics API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/alerts', methods=['POST'])
def api_rapid_alerts_create():
    """Create new alert"""
    try:
        from database import AlertsRepository, Alert
        from datetime import datetime

        data = request.get_json()

        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400

        # Create alert
        alert = Alert(
            level=data.get('level', 'INFO'),
            message=data['message'],
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            active=data.get('active', True),
            metadata=data.get('metadata')
        )

        repo = AlertsRepository()
        alert_id = repo.create(alert)

        if alert_id:
            return jsonify({
                'success': True,
                'alert_id': alert_id
            })
        else:
            return jsonify({'error': 'Failed to create alert'}), 500

    except Exception as e:
        logger.error(f"Create alert API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/alerts/<int:alert_id>/resolve', methods=['PUT'])
def api_rapid_alerts_resolve(alert_id):
    """Resolve alert by ID"""
    try:
        from database import AlertsRepository

        repo = AlertsRepository()
        success = repo.resolve(alert_id)

        if success:
            return jsonify({
                'success': True,
                'message': f'Alert {alert_id} resolved'
            })
        else:
            return jsonify({'error': 'Failed to resolve alert'}), 500

    except Exception as e:
        logger.error(f"Resolve alert API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/alerts/cleanup', methods=['DELETE'])
def api_rapid_alerts_cleanup():
    """Cleanup old resolved alerts"""
    try:
        from database import AlertsRepository

        repo = AlertsRepository()
        days = int(request.args.get('days', 30))

        deleted = repo.delete_old(days=days)

        return jsonify({
            'success': True,
            'deleted': deleted,
            'message': f'Deleted {deleted} old alerts'
        })

    except Exception as e:
        logger.error(f"Cleanup alerts API error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Health Check & Monitoring APIs (Phase 5A)
# ============================================================================

# v6.74: 30s TTL cache for /api/health (avoids 3 DB queries per call × 4 calls/min)
_health_cache: dict = {'data': None, 'ts': 0.0, 'status': 200}

@app.route('/api/health')
def api_health():
    """
    Quick health check endpoint.
    Returns basic system status for UI and monitoring.
    Format compatible with frontend health indicator.
    v6.74: 30s TTL cache — avoids fresh HealthChecker() on every call from two 30s pollers.
    """
    import time
    now = time.monotonic()
    if _health_cache['data'] is not None and now - _health_cache['ts'] < 30:
        return jsonify(_health_cache['data']), _health_cache['status']

    try:
        from monitoring import HealthChecker

        checker = HealthChecker()
        result = checker.check_quick()

        # Transform to frontend format
        checks = {}
        issues = []

        for check in result.get('checks', []):
            check_name = check.get('component', 'unknown')
            is_ok = check.get('status') == 'ok'
            detail = check.get('message', '')

            checks[check_name] = {
                'ok': is_ok,
                'detail': detail
            }

            if not is_ok:
                issues.append(f"{check_name}: {detail}")

        # Build response in frontend format
        response = {
            'healthy': result.get('status') == 'ok',
            'checks': checks,
            'issues': issues,
            'timestamp': result.get('timestamp', datetime.now().isoformat())
        }

        status_code = 200 if response['healthy'] else 503

        _health_cache.update({'data': response, 'ts': now, 'status': status_code})
        return jsonify(response), status_code

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'healthy': False,
            'checks': {
                'system': {
                    'ok': False,
                    'detail': f'Health check failed: {str(e)}'
                }
            },
            'issues': [f'Health check failed: {str(e)}'],
            'timestamp': datetime.now().isoformat()
        }), 503


@app.route('/api/health/detailed')
def api_health_detailed():
    """
    Detailed health check endpoint.
    Returns comprehensive system status including all components.
    """
    try:
        from monitoring import HealthChecker

        checker = HealthChecker()
        result = checker.check_all()

        status_code = 200 if result['status'] in ('ok', 'warning') else 503

        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Detailed health check error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Health check failed: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 503


# ============================================================================
# Performance Metrics APIs (Phase 5B)
# ============================================================================

@app.route('/api/metrics/production')
def api_metrics_production():
    """
    Get production-grade monitoring metrics (v6.21)

    Returns:
        - Order success/failure rates
        - Position sync rates
        - API latency percentiles
        - DLQ accumulation
        - Rate limiter usage
        - Health status with alerts
    """
    try:
        from engine.monitoring_metrics import get_metrics_tracker
        from engine.dead_letter_queue import get_dlq

        tracker = get_metrics_tracker()
        metrics = tracker.get_metrics()
        health = tracker.get_health_status()

        # Get DLQ stats
        try:
            dlq = get_dlq()
            dlq_stats = dlq.get_statistics()
        except:
            dlq_stats = {}

        return jsonify({
            'success': True,
            'health': health,
            'metrics': metrics,
            'dlq': dlq_stats,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Production metrics error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/metrics')
def api_metrics():
    """
    Get performance metrics and statistics.
    """
    try:
        from monitoring import get_performance_monitor

        monitor = get_performance_monitor()
        hours = int(request.args.get('hours', 24))

        stats = monitor.get_all_stats(hours=hours)

        return jsonify({
            'success': True,
            'metrics': stats
        })

    except Exception as e:
        logger.error(f"Metrics API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/summary')
def api_metrics_summary():
    """
    Get performance summary (health score).
    """
    try:
        from monitoring import get_performance_monitor

        monitor = get_performance_monitor()
        summary = monitor.get_summary()

        return jsonify({
            'success': True,
            'summary': summary
        })

    except Exception as e:
        logger.error(f"Metrics summary API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/queries')
def api_metrics_queries():
    """
    Get query performance statistics.
    """
    try:
        from monitoring import get_performance_monitor

        monitor = get_performance_monitor()
        component = request.args.get('component', None)
        hours = int(request.args.get('hours', 24))

        stats = monitor.get_query_stats(component=component, hours=hours)

        return jsonify({
            'success': True,
            'component': component,
            'hours': hours,
            'statistics': stats
        })

    except Exception as e:
        logger.error(f"Query metrics API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/repositories')
def api_metrics_repositories():
    """
    Get repository performance statistics.
    """
    try:
        from monitoring import get_performance_monitor

        monitor = get_performance_monitor()
        hours = int(request.args.get('hours', 24))

        stats = monitor.get_repository_stats(hours=hours)

        return jsonify({
            'success': True,
            'hours': hours,
            'repositories': stats
        })

    except Exception as e:
        logger.error(f"Repository metrics API error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Unified Monitoring Dashboard (Phase 5C)
# ============================================================================

@app.route('/api/monitor/status')
def api_monitor_status():
    """
    Unified monitoring dashboard - combines health checks and performance metrics.
    Returns comprehensive system status for monitoring dashboards.
    """
    try:
        from monitoring import HealthChecker, get_performance_monitor

        # Get health checks
        health_checker = HealthChecker()
        health = health_checker.check_all()

        # Get performance metrics
        perf_monitor = get_performance_monitor()
        metrics = perf_monitor.get_summary()

        # Combine into unified status
        status = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': health['status'],
            'health': {
                'status': health['status'],
                'message': health['message'],
                'summary': health['summary'],
                'checks': health['checks']
            },
            'performance': {
                'health_score': metrics['health_score'],
                'status': metrics['status'],
                'avg_query_ms': metrics['avg_query_time_ms'],
                'avg_api_ms': metrics['avg_api_time_ms'],
                'cache_hit_rate': metrics['cache_hit_rate'],
                'api_success_rate': metrics['api_success_rate']
            },
            'system': {
                'uptime_info': 'Available via health checks',
                'database_ok': any(c['component'] == 'database_connectivity' and c['status'] == 'ok' for c in health['checks']),
                'repositories_ok': all(
                    c['status'] == 'ok'
                    for c in health['checks']
                    if 'repository' in c['component']
                )
            }
        }

        # Determine HTTP status code
        status_code = 200 if health['status'] in ('ok', 'warning') else 503

        return jsonify(status), status_code

    except Exception as e:
        logger.error(f"Monitor status API error: {e}")
        return jsonify({
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'error',
            'error': str(e)
        }), 500


@app.route('/api/monitor/dashboard')
def api_monitor_dashboard():
    """
    Complete monitoring dashboard data.
    Includes health, metrics, and database stats.
    """
    try:
        from monitoring import HealthChecker, get_performance_monitor

        # Get all data
        health_checker = HealthChecker()
        perf_monitor = get_performance_monitor()

        health = health_checker.check_all()
        perf_summary = perf_monitor.get_summary()
        all_metrics = perf_monitor.get_all_stats(hours=24)
        repo_stats = perf_monitor.get_repository_stats(hours=24)

        dashboard = {
            'timestamp': datetime.now().isoformat(),
            'overall_health': health['status'],
            'performance_score': perf_summary['health_score'],

            'health_checks': {
                'status': health['status'],
                'message': health['message'],
                'summary': health['summary'],
                'details': health['checks']
            },

            'performance_summary': perf_summary,

            'metrics_24h': {
                'queries': all_metrics['queries'],
                'api': all_metrics['api'],
                'cache': all_metrics['cache'],
                'database': all_metrics['database']
            },

            'repository_performance': repo_stats
        }

        return jsonify({
            'success': True,
            'dashboard': dashboard
        })

    except Exception as e:
        logger.error(f"Monitor dashboard API error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Automatic Monitoring Control APIs (Phase 5D - Bonus)
# ============================================================================

@app.route('/api/monitor/auto/status')
def api_monitor_auto_status():
    """Get automatic monitoring status"""
    try:
        from monitoring import get_auto_monitor

        monitor = get_auto_monitor()
        stats = monitor.get_stats()

        return jsonify({
            'success': True,
            'auto_monitoring': stats
        })

    except Exception as e:
        logger.error(f"Auto monitor status API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitor/auto/start', methods=['POST'])
def api_monitor_auto_start():
    """Start automatic monitoring"""
    try:
        from monitoring import get_auto_monitor

        data = request.get_json() or {}
        interval = data.get('interval', 300)  # 5 minutes default
        threshold = data.get('threshold', 70.0)

        monitor = get_auto_monitor()
        monitor.health_check_interval = interval
        monitor.alert_threshold = threshold
        monitor.start()

        return jsonify({
            'success': True,
            'message': 'Automatic monitoring started',
            'config': {
                'interval': interval,
                'threshold': threshold
            }
        })

    except Exception as e:
        logger.error(f"Auto monitor start API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitor/auto/stop', methods=['POST'])
def api_monitor_auto_stop():
    """Stop automatic monitoring"""
    try:
        from monitoring import get_auto_monitor

        monitor = get_auto_monitor()
        monitor.stop()

        return jsonify({
            'success': True,
            'message': 'Automatic monitoring stopped'
        })

    except Exception as e:
        logger.error(f"Auto monitor stop API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/market')
def api_config_market():
    """Get market configuration (hours, PDT settings) for frontend (v6.x - Single Source of Truth)"""
    try:
        from utils.market_hours import (
            MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
            MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
            PRE_CLOSE_HOUR, PRE_CLOSE_MINUTE,
            MARKET_OPEN_STR, MARKET_CLOSE_STR, PRE_CLOSE_STR
        )

        # Load PDT config from trading.yaml
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'trading.yaml')
        with open(config_path) as f:
            config = yaml.safe_load(f)

        rr = config.get('rapid_rotation', {})

        return jsonify({
            'market_hours': {
                'open_hour': MARKET_OPEN_HOUR,
                'open_minute': MARKET_OPEN_MINUTE,
                'close_hour': MARKET_CLOSE_HOUR,
                'close_minute': MARKET_CLOSE_MINUTE,
                'pre_close_hour': PRE_CLOSE_HOUR,
                'pre_close_minute': PRE_CLOSE_MINUTE,
                'open_str': MARKET_OPEN_STR,
                'close_str': MARKET_CLOSE_STR,
                'pre_close_str': PRE_CLOSE_STR,
            },
            'pdt': {
                'account_threshold': rr.get('pdt_account_threshold', 25000.0),
                'day_trade_limit': rr.get('pdt_day_trade_limit', 3),
                'reserve': rr.get('pdt_reserve', 1),
            },
            'position_limits': {
                'max_positions': rr.get('max_positions', 5),
                'max_position_pct': rr.get('max_position_pct', 10.0),
                'position_size_pct': rr.get('position_size_pct', 1.0),
            },
            'sl_tp': {
                'min_sl_pct': rr.get('min_sl_pct', 2.5),
                'max_sl_pct': rr.get('max_sl_pct', 3.5),
                'min_tp_pct': rr.get('min_tp_pct', 4.5),
                'max_tp_pct': rr.get('max_tp_pct', 8.0),
            }
        })
    except Exception as e:
        logger.error(f"Market config API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/alpaca')
def api_config_alpaca():
    """Get real-time config from Alpaca (account info, market hours, PDT status)"""
    try:
        from utils.market_hours import get_market_hours_from_broker, is_early_close_today
        from utils.account_info import get_account_info_from_broker
        from engine.brokers import AlpacaBroker

        broker = AlpacaBroker(paper=True)

        # Get market hours for today
        market_hours = get_market_hours_from_broker()

        # Get account info
        account_info = get_account_info_from_broker(broker)

        # Get PDT status (if pdt_smart_guard is available)
        pdt_info = {
            'day_trade_count': account_info['day_trade_count'],
            'pattern_day_trader': account_info['pattern_day_trader'],
        }

        return jsonify({
            'market_hours': {
                'open': market_hours['open'],
                'close': market_hours['close'],
                'is_early_close': market_hours['is_early_close'],
                'date': market_hours['date'],
                'source': market_hours['source']
            },
            'account': {
                'equity': account_info['equity'],
                'cash': account_info['cash'],
                'buying_power': account_info['buying_power'],
                'multiplier': account_info['multiplier'],
                'long_market_value': account_info['long_market_value'],
                'source': account_info['source']
            },
            'pdt': pdt_info,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Alpaca config API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/live-prices')
def api_rapid_live_prices():
    """Get real-time prices via Alpaca (v4.7)"""
    try:
        from engine.brokers import AlpacaBroker

        symbols_param = request.args.get('symbols', '')
        symbols = [s.strip().upper() for s in symbols_param.split(',') if s.strip()]

        if not symbols:
            return jsonify({'error': 'No symbols provided'}), 400

        broker = AlpacaBroker(paper=True)

        # Batch fetch
        quotes = broker.get_snapshots(symbols)

        # Convert to JSON-serializable format
        result = {}
        for symbol, quote in quotes.items():
            result[symbol] = {
                'last': quote.last,
                'bid': quote.bid,
                'ask': quote.ask,
                'volume': quote.volume,
                'high': quote.high,
                'low': quote.low,
                'open': quote.open,
                'prev_close': quote.prev_close,
            }

        return jsonify({
            'prices': result,
            'timestamp': datetime.now().isoformat(),
            'source': 'alpaca_realtime'
        })

    except Exception as e:
        logger.error(f"Live prices API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/bars/<symbol>')
def api_rapid_bars(symbol):
    """Get historical OHLCV bars for candlestick chart (v4.8)"""
    try:
        from engine.brokers import AlpacaBroker
        from datetime import datetime, timedelta, timezone

        # Parse parameters
        timeframe_param = request.args.get('timeframe', '1d').lower()
        days = int(request.args.get('days', 30))

        # Map timeframe shortcuts to Alpaca format
        timeframe_map = {
            '1m': '1Min',
            '5m': '5Min',
            '15m': '15Min',
            '1h': '1Hour',
            '1d': '1Day'
        }
        timeframe = timeframe_map.get(timeframe_param, '1Day')

        # Calculate date range
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        # Fetch bars from Alpaca
        broker = AlpacaBroker(paper=True)
        bars = broker.get_bars(
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            limit=500
        )

        # Convert to Chart.js candlestick format
        candlesticks = []
        for bar in bars:
            candlesticks.append({
                'x': bar.timestamp.isoformat(),  # ISO timestamp
                'o': float(bar.open),            # Open
                'h': float(bar.high),            # High
                'l': float(bar.low),             # Low
                'c': float(bar.close),           # Close
                'v': int(bar.volume)             # Volume
            })

        # Get trade markers (buy/sell points)
        markers = _get_trade_markers(symbol, start, end, broker)

        # Calculate indicators
        indicators = _calculate_indicators(candlesticks)

        return jsonify({
            'symbol': symbol.upper(),
            'timeframe': timeframe_param,
            'bars': candlesticks,
            'markers': markers,
            'indicators': indicators,
            'source': 'alpaca_bars'
        })

    except Exception as e:
        logger.error(f"Bars API error for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/rapid/execution-trace')
def api_rapid_execution_trace():
    """Get execution trace for funnel visualization (v6.15)"""
    try:
        import json as _json

        # Default to summary view
        view = request.args.get('view', 'summary')

        cache_dir = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'cache'
        )

        if view == 'full':
            # Full trace with all stock details
            trace_file = os.path.join(cache_dir, 'execution_trace_full.json')
        else:
            # Summary for funnel view
            trace_file = os.path.join(cache_dir, 'execution_trace_summary.json')

        if not os.path.exists(trace_file):
            return jsonify({
                'error': 'No execution trace available',
                'message': 'Run a scan first to generate trace data',
                'available': False
            })

        with open(trace_file, 'r') as f:
            data = _json.load(f)

        # Add cache age
        trace_ts = datetime.fromisoformat(data['timestamp'])
        cache_age = (datetime.now() - trace_ts).total_seconds()
        data['cache_age_seconds'] = round(cache_age, 0)
        data['status'] = 'fresh' if cache_age < 1200 else 'stale'
        data['available'] = True

        return jsonify(data)

    except Exception as e:
        logger.error(f"Execution trace API error: {e}")
        return jsonify({'error': str(e), 'available': False}), 500


def _get_trade_markers(symbol, start, end, broker):
    """Get buy/sell markers from trade history"""
    try:
        fills = broker.get_activities(activity_types='FILL', days=365)

        markers = []
        for fill in fills:
            # Filter by symbol and date range
            if fill.symbol == symbol:
                fill_time = fill.transaction_time
                if start <= fill_time <= end:
                    markers.append({
                        'time': fill_time.isoformat(),
                        'price': float(fill.price),
                        'side': fill.side,  # 'buy' or 'sell'
                        'qty': float(fill.qty),
                        'order_id': fill.order_id
                    })

        return markers

    except Exception as e:
        logger.warning(f"Could not fetch trade markers: {e}")
        return []


def _calculate_indicators(bars):
    """Calculate technical indicators from bars"""
    if not bars or len(bars) < 20:
        return {}

    try:
        closes = [b['c'] for b in bars]
        volumes = [b['v'] for b in bars]

        # Moving Averages
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None

        # RSI (simple 14-period)
        rsi = None
        if len(closes) >= 14:
            gains = []
            losses = []
            for i in range(1, 15):
                change = closes[-i] - closes[-i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))

            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14

            if avg_loss != 0:
                rs = avg_gain / avg_loss
                rsi = round(100 - (100 / (1 + rs)), 2)
            else:
                rsi = 100

        # Volume average
        avg_volume = sum(volumes[-20:]) / min(20, len(volumes))

        return {
            'ma20': round(ma20, 2) if ma20 else None,
            'ma50': round(ma50, 2) if ma50 else None,
            'rsi': rsi,
            'avg_volume': int(avg_volume),
            'current_price': closes[-1] if closes else None
        }

    except Exception as e:
        logger.warning(f"Indicator calculation error: {e}")
        return {}


# =============================================================================
# AUTO TRADING API ENDPOINTS (Phase 4)
# =============================================================================

# Global auto trading engine instance
_auto_trading_engine = None
_engine_lock = threading.Lock()  # v6.3: Thread-safe singleton
_last_position_refresh: float = 0.0          # v6.73: throttle _load_positions_state
_POSITION_REFRESH_INTERVAL: float = 5.0     # seconds — one DB read per 5s max

def get_auto_trading_engine():
    """Get or create auto trading engine singleton (thread-safe).

    v6.56: Always refreshes positions from DB before returning so that
    app.py never serves stale in-memory state from a previous session.
    The nohup engine is the true owner of positions — it writes to DB;
    app.py reads DB here to stay in sync without any IPC needed.

    v6.73: Throttle _load_positions_state to once per 5s. background_monitor
    calls get_auto_trading_engine() 3x per 10s heavy cycle; without throttle
    all three trigger a DB read in the same second.
    """
    global _auto_trading_engine, _last_position_refresh
    # Fast path: already created — refresh positions from DB (throttled) then return
    if _auto_trading_engine is not None:
        import time as _time
        now = _time.monotonic()
        if now - _last_position_refresh >= _POSITION_REFRESH_INTERVAL:
            try:
                _auto_trading_engine._load_positions_state()
                _last_position_refresh = now
            except Exception as _e:
                logger.debug(f"Position refresh skipped: {_e}")
        return _auto_trading_engine
    # Slow path: create with lock
    with _engine_lock:
        # Double-check inside lock
        if _auto_trading_engine is not None:
            return _auto_trading_engine
        try:
            from auto_trading_engine import AutoTradingEngine
            # Credentials from environment
            API_KEY = os.environ.get('ALPACA_API_KEY')
            SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY')
            if not API_KEY or not SECRET_KEY:
                logger.error("ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables required")
                return None
            _auto_trading_engine = AutoTradingEngine(
                api_key=API_KEY,
                secret_key=SECRET_KEY,
                paper=True,
                auto_start=False  # v6.73: app.py is display-only — nohup engine owns trading loop
            )
        except Exception as e:
            logger.error(f"Failed to create auto trading engine: {e}")
            return None
    return _auto_trading_engine


def convert_numpy_types(obj):
    """Convert numpy/pandas/datetime types to native Python types for JSON serialization"""
    import numpy as np
    import pandas as pd
    from datetime import datetime, date

    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    else:
        return obj


# v6.74: 30s TTL cache for /api/auto/status (avoids broker.get_account() + get_clock() on every browser poll)
_auto_status_cache: dict = {'data': None, 'ts': 0.0}
_status_cache_lock = threading.Lock()  # v7.2: RC-3 guard for _auto_status_cache

@app.route('/api/auto/status')
def api_auto_status():
    """Get auto trading engine status.
    v6.74: 30s TTL cache — engine.get_status() makes 2 Alpaca API calls (get_account + get_clock).
    """
    import time as _time
    now = _time.monotonic()
    with _status_cache_lock:
        if _auto_status_cache['data'] is not None and now - _auto_status_cache['ts'] < 30:
            return jsonify(_auto_status_cache['data'])

    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        status = engine.get_status()
        # Convert numpy types to native Python types
        status = convert_numpy_types(status)

        # v6.37: Read cron_schedule from file (written by standalone engine)
        try:
            # Path: src/web/app.py → src/web → src → project_root → data/cron_schedule.json
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            cron_file = os.path.join(project_root, 'data', 'cron_schedule.json')
            if os.path.exists(cron_file):
                with open(cron_file, 'r') as f:
                    cron_data = json.load(f)
                status['cron_schedule'] = cron_data
                # v7.8: Override daily_stats with engine's authoritative copy
                if 'daily_stats' in cron_data:
                    status['daily_stats'] = cron_data['daily_stats']
                logger.debug(f"✅ Loaded cron_schedule from {cron_file}")
            else:
                logger.debug(f"⚠️ cron_schedule file not found: {cron_file}")
        except Exception as e:
            logger.error(f"Could not read cron_schedule from file: {e}")

        with _status_cache_lock:
            _auto_status_cache.update({'data': status, 'ts': now})
        return jsonify(status)

    except Exception as e:
        logger.error(f"Auto status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto/start', methods=['POST'])
def api_auto_start():
    """Start auto trading engine"""
    try:
        # v6.84: Check if nohup engine is already running via heartbeat.
        # If alive, don't start webapp engine — it would run a duplicate trading loop
        # alongside the systemd-managed nohup engine (causes duplicate scans/SELLs).
        try:
            from database.repositories.heartbeat_repository import HeartbeatRepository
            hb = HeartbeatRepository().read(max_age_seconds=60)
            if hb.get('alive'):
                return jsonify({'message': 'Engine running (systemd)', 'running': True})
        except Exception:
            pass

        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        if engine.running:
            return jsonify({'message': 'Already running', 'running': True})

        engine.start()
        return jsonify({'message': 'Auto trading started', 'running': True})

    except Exception as e:
        logger.error(f"Auto start error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto/stop', methods=['POST'])
def api_auto_stop():
    """Stop auto trading engine"""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        engine.stop()
        return jsonify({'message': 'Auto trading stopped', 'running': False})

    except Exception as e:
        logger.error(f"Auto stop error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto/emergency-stop', methods=['POST'])
def api_auto_emergency_stop():
    """Activate emergency stop"""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        engine.safety.activate_emergency_stop("Web UI triggered")
        engine.stop()

        # Alert: Emergency stop
        try:
            from alert_manager import get_alert_manager
            get_alert_manager().alert_emergency_stop("Activated from Web UI")
        except Exception:
            pass

        return jsonify({
            'message': 'Emergency stop activated',
            'emergency_stop': True
        })

    except Exception as e:
        logger.error(f"Emergency stop error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto/emergency-reset', methods=['POST'])
def api_auto_emergency_reset():
    """Deactivate emergency stop"""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        engine.safety.deactivate_emergency_stop()

        return jsonify({
            'message': 'Emergency stop deactivated',
            'emergency_stop': False
        })

    except Exception as e:
        logger.error(f"Emergency reset error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cron/status')
def api_cron_status():
    """Get cron jobs status"""
    try:
        status_file = os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'cron_status.json'
        )
        if os.path.exists(status_file):
            with open(status_file, 'r') as f:
                status = json.load(f)
        else:
            status = {}

        # Add schedule info
        schedule = {
            'health_check': {'interval': '*/5 * * * *', 'desc': 'Every 5 min'},
            'alert_cleanup': {'interval': '0 4 * * *', 'desc': '04:00 daily'},
            'log_cleanup': {'interval': '30 4 * * *', 'desc': '04:30 daily'},
            'outcome_tracker': {'interval': '0 5 * * 2-6', 'desc': '05:00 Tue-Sat'},
            'prefilter_evening': {'interval': '0 8 * * 2-6', 'desc': '08:00 Tue-Sat'},
            'prefilter_pre_open': {'interval': '0 21 * * 1-5', 'desc': '21:00 Mon-Fri'},
            'universe_maintenance': {'interval': '0 3 * * 0', 'desc': '03:00 Sunday'},
            'db_backup': {'interval': '0 6 * * 0', 'desc': '06:00 Sunday'}
        }

        return jsonify({
            'status': status,
            'schedule': schedule,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Cron status error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto/close-all', methods=['POST'])
@require_api_auth
def api_auto_close_all():
    """Emergency close ALL positions at market. Sells everything via Alpaca."""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        # v4.9 Fix #33: Prevent concurrent close-all
        if not engine._close_all_lock.acquire(blocking=False):
            return jsonify({'error': 'Close-all already in progress'}), 409

        try:
            return _do_close_all(engine)
        finally:
            engine._close_all_lock.release()

    except Exception as e:
        logger.error(f"Close-all error: {e}")
        return jsonify({'error': str(e)}), 500


def _do_close_all(engine):
    """Internal close-all logic (runs under _close_all_lock)."""
    try:
        # 1. Stop engine first
        engine.safety.activate_emergency_stop("Close-all from Web UI")
        engine.stop()

        # 2. Get all positions from Alpaca
        positions = engine.broker.get_positions()
        if not positions:
            return jsonify({'message': 'No positions to close', 'closed': []})

        results = []
        for pos in positions:
            try:
                qty = int(float(pos.qty))
                if qty <= 0:
                    continue
                sell_order = engine.broker.place_market_sell(pos.symbol, qty)
                status = 'submitted'
                if sell_order:
                    # Wait briefly for fill
                    import time
                    for _wait in range(5):
                        time.sleep(1)
                        check = engine.broker.get_order(sell_order.id)
                        if check.status == 'filled':
                            status = 'filled'
                            break
                    else:
                        status = check.status if check else 'unknown'
                results.append({
                    'symbol': pos.symbol,
                    'qty': qty,
                    'status': status,
                })
                logger.warning(f"CLOSE-ALL: {pos.symbol} x{qty} → {status}")
            except Exception as e:
                results.append({
                    'symbol': pos.symbol,
                    'qty': int(float(pos.qty)),
                    'status': f'error: {e}',
                })
                logger.error(f"CLOSE-ALL: Failed to sell {pos.symbol}: {e}")

        # 3. Clear engine tracked positions
        with engine._positions_lock:
            engine.positions.clear()
        engine._save_positions_state()

        # 4. Alert
        try:
            from alert_manager import get_alert_manager
            symbols = [r['symbol'] for r in results]
            get_alert_manager().add(
                level='CRITICAL',
                title='CLOSE ALL EXECUTED',
                message=f"Emergency close-all: {', '.join(symbols)}",
                category='emergency',
            )
        except Exception:
            pass

        return jsonify({
            'message': f'Closed {len(results)} positions',
            'closed': results,
            'emergency_stop': True,
        })

    except Exception as e:
        logger.error(f"Close-all internal error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto/heartbeat')
def api_auto_heartbeat():
    """v4.7 Fix #15: Get engine heartbeat status (v6.72: DB-backed)"""
    try:
        from engine.state_manager import read_heartbeat
        hb = read_heartbeat(max_age_seconds=120)
        return jsonify(hb)
    except Exception as e:
        return jsonify({'alive': False, 'stale': True, 'error': str(e)}), 500


@app.route('/api/auto/positions')
def api_auto_positions():
    """Get live positions from Alpaca"""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        # Get positions status
        positions = engine.get_positions_status()

        # Get account info
        account = engine.broker.get_account()

        return jsonify({
            'positions': positions,
            'account': {
                'cash': getattr(account, 'cash', 0),
                'portfolio_value': getattr(account, 'portfolio_value', 0),
                'buying_power': getattr(account, 'buying_power', 0),
            }
        })

    except Exception as e:
        logger.error(f"Auto positions error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto/scan', methods=['POST'])
def api_auto_scan():
    """Manually trigger a scan"""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        signals = engine.scan_for_signals()

        return jsonify({
            'signals': [
                {
                    'symbol': s.symbol,
                    'score': getattr(s, 'score', 0),
                    'entry_price': getattr(s, 'entry_price', getattr(s, 'close', 0)),
                    'sector': getattr(s, 'sector', 'Unknown'),
                }
                for s in signals[:10]
            ],
            'count': len(signals)
        })

    except Exception as e:
        logger.error(f"Auto scan error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto/execute', methods=['POST'])
@require_api_auth
def api_auto_execute():
    """Manually execute a signal (semi-auto mode)"""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return jsonify({'error': 'Engine not available'}), 500

        data = request.get_json()
        symbol = data.get('symbol')

        if not symbol:
            return jsonify({'error': 'Symbol required'}), 400

        # v4.9 Fix #39: Reject if engine is currently scanning (race condition)
        from auto_trading_engine import TradingState
        if engine.state == TradingState.SCANNING:
            return jsonify({'error': 'Engine is currently scanning — try again in a moment'}), 409

        # Check if market is open
        if not engine.broker.is_market_open():
            return jsonify({'error': 'Market is closed'}), 400

        # Safety check
        can_trade, reason = engine.safety.can_open_new_position()
        if not can_trade:
            return jsonify({'error': f'Safety block: {reason}'}), 400

        # Find signal for this symbol
        signals = engine.scan_for_signals()
        signal = next((s for s in signals if s.symbol == symbol), None)

        if not signal:
            return jsonify({'error': f'No valid signal for {symbol}'}), 400

        # Execute
        success = engine.execute_signal(signal)

        if success:
            return jsonify({
                'message': f'Executed buy for {symbol}',
                'success': True
            })
        else:
            return jsonify({'error': 'Execution failed'}), 500

    except Exception as e:
        logger.error(f"Auto execute error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================
# WebSocket Event Handlers (v4.0 Real-time)
# ============================================

# Store connected clients
_clients_lock = threading.Lock()
connected_clients = set()
# Background monitor state
monitor_thread = None
monitor_running = False

@socketio.on('connect')
def handle_connect():
    """Client connected"""
    with _clients_lock:
        connected_clients.add(request.sid)
        client_count = len(connected_clients)
    logger.info(f"WebSocket client connected: {request.sid} (total: {client_count})")
    # Send initial data immediately
    emit('connected', {'status': 'connected', 'clients': int(client_count)})

@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    with _clients_lock:
        connected_clients.discard(request.sid)
        client_count = len(connected_clients)
    logger.info(f"WebSocket client disconnected: {request.sid} (total: {client_count})")

@socketio.on('request_update')
def handle_request_update(data=None):
    """Client requests immediate update"""
    # v6.45: Convert numpy types before emit to prevent JSON serialization errors
    emit('positions_update', convert_numpy_types(get_positions_data()))
    emit('signals_update', convert_numpy_types(get_signals_data()))
    emit('status_update', convert_numpy_types(get_status_data()))
    emit('regime_update', convert_numpy_types(get_regime_data()))

def _get_extended_hours_prices(symbols: list) -> dict:
    """
    Get extended hours prices using yfinance.
    Returns {symbol: {premarket_price, premarket_change, premarket_session, regular_close}}

    v6.24: Switched from Alpaca snapshots to yfinance for reliability.
    v6.47: Add pre-market price support + return regular_close for "N" display.
    """
    results = {}
    if not symbols:
        return results

    try:
        import yfinance as yf
        import pytz

        et_tz = pytz.timezone('America/New_York')
        now_et = datetime.now(et_tz)
        et_mins = now_et.hour * 60 + now_et.minute

        # ET session windows (in minutes from midnight)
        PRE_MARKET_START = 4 * 60       # 04:00 ET
        PRE_MARKET_END   = 9 * 60 + 30  # 09:30 ET
        AFTER_HOURS_START = 16 * 60     # 16:00 ET
        AFTER_HOURS_END   = 20 * 60     # 20:00 ET

        is_premarket  = PRE_MARKET_START  <= et_mins < PRE_MARKET_END
        is_afterhours = AFTER_HOURS_START <= et_mins < AFTER_HOURS_END

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info

                regular_close = info.get('regularMarketPrice', 0)
                after_hours   = info.get('postMarketPrice', None)
                pre_market    = info.get('preMarketPrice', None)

                # Pick extended price based on current ET session
                ext_price = None
                session   = None
                if is_premarket and pre_market and regular_close > 0:
                    ext_price = pre_market
                    session   = 'Pre'
                elif is_afterhours and after_hours and regular_close > 0:
                    ext_price = after_hours
                    session   = 'AH'
                elif after_hours and regular_close > 0:
                    # Outside AH window but stale AH data still available
                    ext_price = after_hours
                    session   = 'AH'

                if ext_price and regular_close > 0:
                    change = ((ext_price - regular_close) / regular_close) * 100
                    # Only include if there's actual movement (> 0.01%)
                    if abs(change) > 0.01:
                        results[symbol] = {
                            'premarket_price':   round(ext_price, 2),
                            'premarket_change':  round(change, 2),
                            'premarket_session': session,
                            'regular_close':     round(regular_close, 2),
                        }
                        logger.debug(f"{session}: {symbol} ${ext_price:.2f} ({change:+.2f}% vs ${regular_close:.2f})")
            except Exception as e:
                logger.debug(f"Failed to fetch extended hours price for {symbol}: {e}")
                continue

    except Exception as e:
        logger.warning(f"Extended hours price error: {e}")

    return results


def _build_positions_from_file():
    """
    Build position data from rapid_portfolio.json when engine not running.

    v4.8: Fallback mechanism for displaying positions when engine is offline.
    Fetches fresh prices from yfinance for each position.
    Reads directly from JSON file to avoid PositionManager compatibility issues.
    """
    import json
    import os
    from rapid_portfolio_manager import RapidPortfolioManager

    # Read portfolio file directly
    portfolio_file = 'rapid_portfolio.json'
    if not os.path.exists(portfolio_file):
        logger.warning("rapid_portfolio.json not found")
        return [], {'positions': 0, 'total_pnl_usd': 0, 'total_pnl_pct': 0}

    try:
        with open(portfolio_file, 'r') as f:
            portfolio_data = json.load(f)
        positions = portfolio_data.get('positions', {})
    except Exception as e:
        logger.error(f"Failed to read rapid_portfolio.json: {e}")
        return [], {'positions': 0, 'total_pnl_usd': 0, 'total_pnl_pct': 0}

    if not positions:
        return [], {'positions': 0, 'total_pnl_usd': 0, 'total_pnl_pct': 0}

    # Create RapidPortfolioManager instance for price fetching
    pm = RapidPortfolioManager()

    statuses_data = []
    total_pnl_usd = 0.0

    for symbol, pos in positions.items():
        try:
            # Fetch current price using updated get_current_price() method
            current_price = pm.get_current_price(symbol)
            if not current_price:
                logger.warning(f"{symbol}: Failed to fetch current price, using entry price")
                current_price = pos.get('entry_price', 0)

            entry_price = pos.get('entry_price', 0)
            qty = pos.get('qty', 0)

            # Calculate P/L
            pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
            pnl_usd = (current_price - entry_price) * qty
            total_pnl_usd += pnl_usd

            # Get position details from file
            stop_loss = pos.get('current_sl_price', entry_price * 0.96)
            take_profit = pos.get('tp_price', entry_price * 1.08)
            peak_price = pos.get('peak_price', current_price)
            trailing_active = pos.get('trailing_active', False)

            # Calculate days held
            entry_time_str = pos.get('entry_time', '')
            try:
                entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                days_held = max(0, (datetime.now() - entry_time).days)
            except:
                days_held = 0

            # Determine signal type
            if take_profit > 0 and current_price >= take_profit:
                signal = 'TAKE_PROFIT'
                action = f'Take profit target ${take_profit:.2f} reached'
            elif current_price <= stop_loss:
                signal = 'CRITICAL'
                action = f'Price at/below stop loss ${stop_loss:.2f}'
            elif pnl_pct <= -2.0:
                signal = 'WARNING'
                action = f'Down {pnl_pct:.1f}% — monitor closely'
            elif days_held >= 5:
                signal = 'WARNING'
                action = f'Held {days_held} days — consider exit'
            elif pnl_pct >= 3.0:
                signal = 'HOLD'
                action = f'Profitable +{pnl_pct:.1f}% — trailing {"active" if trailing_active else "pending"}'
            else:
                signal = 'HOLD'
                action = 'Position within normal range'

            pos_data = {
                'symbol': symbol,
                'entry_price': entry_price,
                'current_price': current_price,
                'pnl_pct': round(pnl_pct, 2),
                'pnl_usd': round(pnl_usd, 2),
                'days_held': days_held,
                'signal': signal,
                'reasons': [],
                'action': action,
                'new_candidates': [],
                'shares': qty,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'trailing_active': trailing_active,
                'highest_price': peak_price,
                'sl_pct': pos.get('sl_pct', 4.0),
                'tp_pct': pos.get('tp_pct', 8.0),
                'atr_pct': pos.get('atr_pct', 3.0),
            }

            statuses_data.append(pos_data)

        except Exception as e:
            logger.error(f"Error building position data for {symbol}: {e}")
            continue

    summary = {
        'positions': len(statuses_data),
        'total_pnl_usd': round(total_pnl_usd, 2),
        'total_pnl_pct': round(sum(s['pnl_pct'] for s in statuses_data) / max(len(statuses_data), 1), 2),
    }

    return statuses_data, summary


def _build_positions_from_engine():
    """Build position data from DB + Alpaca live prices.

    Returns (statuses_data, summary) or raises on error.
    This is the single source of truth — used by both REST and WebSocket.

    v4.8: Added fallback to RapidPortfolioManager when engine not running
    v6.56: Refresh positions from DB so app.py reflects nohup engine's current state
    v6.69: Read from PositionRepository (DB) directly instead of engine.positions.
           engine.positions in app.py singleton was never updated after the nohup engine
           bought new positions — MRVL invisible until app restart. DB is always current.
    """
    engine = get_auto_trading_engine()

    # v6.69: Read from DB (always fresh) — engine.positions is stale in app.py singleton
    db_positions = []
    try:
        from database import PositionRepository
        db_positions = PositionRepository().get_all(use_cache=False)
    except Exception as _e:
        logger.warning(f"DB position read failed: {_e}")

    if not db_positions:
        # v6.80: rapid_portfolio.json removed in v6.72 DB migration — return empty directly
        return [], {'positions': 0, 'total_pnl_usd': 0, 'total_pnl_pct': 0}

    if not engine:
        logger.warning("Engine not available — cannot fetch live prices")
        return [], {'positions': 0, 'total_pnl_usd': 0, 'total_pnl_pct': 0}

    # Fetch live prices from Alpaca in one call
    symbols = [p.symbol for p in db_positions]
    alpaca_prices = {}
    try:
        for pos in engine.broker.get_positions():
            alpaca_prices[pos.symbol] = {
                'current_price': pos.current_price,
                'unrealized_pl': pos.unrealized_pl,
                'unrealized_plpc': pos.unrealized_plpc,
            }
    except Exception as e:
        logger.warning(f"Failed to fetch Alpaca prices: {e}")

    try:
        market_open = engine.broker.is_market_open() if engine.broker else True
    except Exception:
        market_open = False  # Alpaca unreachable — default to closed (safe for weekend)

    # v6.48: When market closed, fetch official close from Alpaca Bars API (IEX feed).
    # "N" = IEX regular-hours close (reliable).
    # "AH/Pre" = Alpaca positions current_price (includes AH/pre-market) — replaces yfinance.
    alpaca_bar_closes = {}
    if not market_open and engine.broker:
        try:
            for symbol in symbols:
                bars = engine.broker.get_bars(symbol, timeframe='1Day', limit=10)
                if bars:
                    b = bars[-1]  # Most recent bar (ascending chronological order)
                    close = getattr(b, 'c', None) or getattr(b, 'close', None)
                    if close:
                        alpaca_bar_closes[symbol] = float(close)
            if alpaca_bar_closes:
                logger.debug(f"Alpaca Bars closes: { {s: f'${v:.2f}' for s, v in alpaca_bar_closes.items()} }")
        except Exception as e:
            logger.warning(f"Failed to fetch Alpaca Bars close: {e}")

    # v6.48: ET session detection for AH/Pre label
    import pytz as _pytz
    _et_tz = _pytz.timezone('America/New_York')
    _now_et = datetime.now(_et_tz)
    _et_mins = _now_et.hour * 60 + _now_et.minute
    _is_premarket  = (4 * 60) <= _et_mins < (9 * 60 + 30)
    _is_afterhours = (16 * 60) <= _et_mins < (20 * 60)

    logger.debug(f"Portfolio API: market_open={market_open}, premarket={_is_premarket}, afterhours={_is_afterhours}")

    # v7.3: yfinance 1m prepost=True for AH/pre-market prices (replaces Alpaca IEX — poor ext-hours coverage).
    # Works for AH (4pm–8pm ET), pre-market (4am–9:30am ET), and overnight OVN positions.
    # period='2d' ensures today's data is always in window. Session label derived from bar timestamp.
    yf_ext_prices = {}  # {symbol: (price, 'AH'|'Pre')}
    if not market_open and symbols:
        try:
            import yfinance as yf
            _today_et2 = datetime.now(_et_tz).date()
            _df_ext = yf.download(
                symbols if len(symbols) > 1 else symbols[0],
                period='2d', interval='1m', prepost=True,
                auto_adjust=True, progress=False,
            )
            if not _df_ext.empty:
                _close = _df_ext['Close']
                for _sym in symbols:
                    try:
                        _s = (_close[_sym] if len(symbols) > 1 else _close).squeeze().dropna()
                        if _s.empty:
                            continue
                        # Prefer today's pre-market bars; fall back to yesterday's AH
                        _today_mask = _s.index.tz_convert(_et_tz).date == _today_et2
                        _today_bars = _s[_today_mask]
                        if not _today_bars.empty:
                            _price = float(_today_bars.iloc[-1])
                            _ts = _today_bars.index[-1].tz_convert(_et_tz)
                            _m = _ts.hour * 60 + _ts.minute
                            if _m < 9 * 60 + 30:
                                _sess = 'Pre'
                            elif _m >= 16 * 60:
                                _sess = 'AH'
                            else:
                                continue  # regular-hours bar — skip
                        else:
                            # No today bars yet (early pre-market) — use yesterday's AH close
                            _yest = _today_et2 - timedelta(days=1)
                            _yest_mask = _s.index.tz_convert(_et_tz).date == _yest
                            _yest_bars = _s[_yest_mask]
                            _ah_bars = _yest_bars[_yest_bars.index.tz_convert(_et_tz).hour >= 16]
                            if _ah_bars.empty:
                                continue
                            _price = float(_ah_bars.iloc[-1])
                            _ts = _ah_bars.index[-1].tz_convert(_et_tz)
                            _sess = 'AH'
                        yf_ext_prices[_sym] = (_price, _sess)
                        logger.debug(f"yf {_sess} {_sym}: ${_price:.2f} @ {_ts}")
                    except Exception as _e2:
                        logger.debug(f"yf ext {_sym}: {_e2}")
        except Exception as _e:
            logger.debug(f"yfinance ext price fetch failed: {_e}")

    statuses_data = []
    total_pnl_usd = 0.0

    # v6.69: Iterate DB positions (always current) instead of stale engine.positions
    for db_pos in db_positions:
        symbol       = db_pos.symbol
        entry_price  = db_pos.entry_price
        qty          = db_pos.qty
        stop_loss    = db_pos.stop_loss
        take_profit  = db_pos.take_profit or 0.0
        trailing_act = bool(db_pos.trailing_stop)
        peak_price   = db_pos.peak_price or entry_price
        sl_pct       = db_pos.sl_pct or 2.5
        tp_pct       = db_pos.tp_pct or 5.0
        atr_pct      = db_pos.entry_atr_pct or 0.0
        days_held    = db_pos.day_held or 0
        source       = db_pos.source or 'dip_bounce'

        ap = alpaca_prices.get(symbol, {})

        # v6.48: "N" price source:
        # - Market OPEN: Alpaca positions live price (real-time)
        # - Market CLOSED: Alpaca Bars IEX close (regular-hours only, not AH/pre-market)
        if market_open:
            current_price = float(ap.get('current_price') or entry_price)
        else:
            current_price = float(
                alpaca_bar_closes.get(symbol)
                or ap.get('current_price')
                or entry_price
            )
        logger.debug(f"{symbol}: current_price=${current_price:.2f} source={'live' if market_open else 'IEX_close'} (market_open={market_open})")

        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        pnl_usd = (current_price - entry_price) * qty
        total_pnl_usd += pnl_usd

        # Determine signal type
        if take_profit > 0 and current_price >= take_profit:
            signal = 'TAKE_PROFIT'
            action = f'Take profit target ${take_profit:.2f} reached'
        elif current_price <= stop_loss:
            signal = 'CRITICAL'
            action = f'Price at/below stop loss ${stop_loss:.2f}'
        elif pnl_pct <= -2.0:
            signal = 'WARNING'
            action = f'Down {pnl_pct:.1f}% — monitor closely'
        elif days_held >= 5:
            signal = 'WARNING'
            action = f'Held {days_held} days — consider exit'
        elif pnl_pct >= 3.0:
            signal = 'HOLD'
            action = f'Profitable +{pnl_pct:.1f}% — trailing {"active" if trailing_act else "pending"}'
        else:
            signal = 'HOLD'
            action = 'Position within normal range'

        pos_data = {
            'symbol': symbol,
            'entry_price': entry_price,
            'current_price': current_price,
            'pnl_pct': round(pnl_pct, 2),
            'pnl_usd': round(pnl_usd, 2),
            'days_held': days_held,
            'signal': signal,
            'reasons': [],
            'action': action,
            'new_candidates': [],
            'shares': qty,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'trailing_active': trailing_act,
            'highest_price': peak_price,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'atr_pct': atr_pct,
            'source': source,
        }

        # v7.3: AH/Pre price from yfinance (replaces IEX minute bars + positions.current_price fallback).
        # Covers AH (4pm–8pm ET), pre-market (4am–9:30am ET), and overnight OVN positions.
        if not market_open and symbol in yf_ext_prices:
            yf_live, yf_session = yf_ext_prices[symbol]
            change_pct = (yf_live - current_price) / current_price * 100
            if abs(change_pct) > 0.05:  # > 0.05% = real movement
                pos_data['premarket_price']   = round(yf_live, 2)
                pos_data['premarket_change']  = round(change_pct, 2)
                pos_data['premarket_session'] = yf_session
                ah_pnl_pct = ((yf_live - entry_price) / entry_price) * 100
                ah_pnl_usd = (yf_live - entry_price) * qty
                total_pnl_usd += ah_pnl_usd - pnl_usd
                pos_data['current_price'] = round(yf_live, 2)
                pos_data['pnl_pct'] = round(ah_pnl_pct, 2)
                pos_data['pnl_usd'] = round(ah_pnl_usd, 2)
                if abs(change_pct) >= 1.0:
                    logger.info(f"{symbol}: {yf_session} ${yf_live:.2f} ({change_pct:+.2f}% vs close ${current_price:.2f})")
                else:
                    logger.debug(f"{symbol}: {yf_session} ${yf_live:.2f} ({change_pct:+.2f}% vs close ${current_price:.2f})")

                # Recalculate signal when move is significant (>2%)
                if abs(change_pct) >= 2.0:
                    if take_profit > 0 and yf_live >= take_profit:
                        pos_data['signal'] = 'TAKE_PROFIT'
                        pos_data['action'] = f'{yf_session} price ${yf_live:.2f} reached TP ${take_profit:.2f}'
                    elif yf_live <= stop_loss:
                        pos_data['signal'] = 'CRITICAL'
                        pos_data['action'] = f'{yf_session} ${yf_live:.2f} below SL ${stop_loss:.2f} — gap risk at open'
                    elif ah_pnl_pct <= -2.0:
                        pos_data['signal'] = 'WARNING'
                        pos_data['action'] = f'{yf_session} down {ah_pnl_pct:.1f}% — monitor at open'
                    elif ah_pnl_pct >= 3.0:
                        pos_data['signal'] = 'HOLD'
                        pos_data['action'] = f'{yf_session} +{ah_pnl_pct:.1f}% — trailing {"active" if trailing_act else "pending"}'
                    else:
                        pos_data['signal'] = 'HOLD'
                        pos_data['action'] = f'{yf_session} {ah_pnl_pct:+.1f}% — within normal range'
                    logger.info(f"{symbol}: {yf_session} signal updated → {pos_data['signal']} ({ah_pnl_pct:.1f}%)")

        statuses_data.append(pos_data)

    summary = {
        'positions': len(statuses_data),
        'total_pnl_usd': round(total_pnl_usd, 2),
        'total_pnl_pct': round(sum(s['pnl_pct'] for s in statuses_data) / max(len(statuses_data), 1), 2),
    }

    return statuses_data, summary


def get_positions_data():
    """Get current positions data for WebSocket — reads from engine"""
    try:
        statuses_data, summary = _build_positions_from_engine()
        return {'statuses': statuses_data, 'summary': summary}
    except Exception as e:
        logger.error(f"WebSocket positions error: {e}")
        return {'error': str(e)}

def get_signals_data():
    """Get current signals data for WebSocket.

    v6.73 FIX: Read active signals from DB (written by nohup engine) instead of
    calling engine.scan_for_signals() which triggers a full 250-stock yfinance scan
    every 10s from background_monitor. DB read is O(1) vs ~3 minute scan.
    """
    try:
        from database.repositories.signal_repository import SignalRepository
        signals = SignalRepository().get_active()
        result = []
        for s in signals:
            price = s.signal_price or 0.0
            sl = s.stop_loss or 0.0
            tp = s.take_profit or 0.0
            result.append({
                'symbol': s.symbol,
                'score': s.score,
                'entry_price': price,
                'stop_loss': sl,
                'take_profit': tp,
                'rsi': s.rsi,
                'momentum_5d': s.momentum_5d,
                'momentum_20d': s.momentum_20d,
                'distance_from_high': s.distance_from_high,
                'new_score': getattr(s, 'new_score', None),
                'sl_method': s.sl_method,
                'max_loss': abs(sl - price) / price * 100 if price else 0,
                'expected_gain': abs(tp - price) / price * 100 if price else 0,
                'volume_ratio': s.volume_ratio or 1.0,
            })
        return {'signals': result, 'count': len(result)}
    except Exception as e:
        logger.error(f"WebSocket signals error: {e}")
        return {'error': str(e)}

def get_status_data():
    """Get auto trading status for WebSocket"""
    try:
        engine = get_auto_trading_engine()
        if not engine:
            return {'error': 'Engine not available'}

        account = engine.broker.get_account()

        # v6.74: Position count from DB (engine.positions is empty in webapp auto_start=False)
        from database.repositories.position_repository import PositionRepository
        try:
            db_pos = PositionRepository().get_all(use_cache=False)
            pos_count = len(db_pos) if db_pos else 0
        except Exception:
            pos_count = 0

        # v6.74: Effective params for mode badge (cached via _check_market_regime 120s)
        try:
            effective_params = engine._get_effective_params()
        except Exception:
            effective_params = {}

        # v6.74: Market regime for bear/bull sector visibility
        try:
            market_regime = get_regime_data().get('regime', 'UNKNOWN')
        except Exception:
            market_regime = 'UNKNOWN'

        # Queue count from DB (engine.signal_queue is stale in webapp auto_start=False)
        try:
            from database.repositories.queue_repository import QueueRepository
            queue_size = len(QueueRepository().get_all(status='waiting') or [])
        except Exception:
            queue_size = 0

        return {
            'running': engine.running,
            'state': engine.state.value if hasattr(engine.state, 'value') else str(engine.state),
            'market_open': engine.broker.is_market_open(),
            'cash': float(getattr(account, 'cash', 0)),
            'account_value': float(getattr(account, 'portfolio_value', 0)),
            'safety': engine.safety.get_status_summary(),
            'positions': pos_count,
            'effective_params': effective_params,
            'market_regime': market_regime,
            'queue_size': queue_size,
        }
    except Exception as e:
        logger.error(f"WebSocket status error: {e}")
        return {'error': str(e)}

def get_regime_data():
    """
    Get SPY regime data for WebSocket

    v6.20 FIX: Use engine (Single Source of Truth) instead of creating new screener
    - OLD: Created RapidRotationScreener() every 10 seconds → expensive initialization
    - NEW: Use engine's regime check → lightweight, has allowed_sectors in BEAR mode
    """
    try:
        # v6.20: Use engine as Single Source of Truth
        # v6.73 FIX: Call _check_market_regime() directly (120s cached) instead of get_status().
        # get_status() calls broker.get_account() (Alpaca API) every invocation — too heavy for
        # background_monitor (every 10s). _check_market_regime() is cached and lightweight.
        engine = get_auto_trading_engine()
        if engine:
            try:
                is_bull, reason = engine._check_market_regime()
                rc = getattr(engine, '_regime_cache', None)
                details = rc[3] if rc and len(rc) >= 4 else {}
                bear_mode = getattr(engine, 'BEAR_MODE_ENABLED', True)
                market_regime = 'BULL' if is_bull else ('BEAR_MODE' if bear_mode else 'BEAR')
                return {
                    'is_bull': is_bull,
                    'reason': reason,
                    'details': details,
                    'regime': market_regime
                }
            except Exception as _regime_err:
                logger.debug(f"_check_market_regime error: {_regime_err}")

        # Fallback: Lightweight SPY check (no full screener initialization!)
        import yfinance as yf
        spy = yf.Ticker('SPY')
        hist = spy.history(period='1mo')
        if len(hist) >= 20:
            sma20 = hist['Close'].rolling(20).mean().iloc[-1]
            current = hist['Close'].iloc[-1]
            is_bull = current > sma20
            pct_diff = ((current - sma20) / sma20) * 100
            return {
                'is_bull': is_bull,
                'reason': f"SPY ${current:.2f} {'>' if is_bull else '<'} SMA20 ${sma20:.2f} ({pct_diff:+.1f}%)",
                'details': {'spy': float(current), 'sma20': float(sma20)},
                'regime': 'BULL' if is_bull else 'BEAR'
            }
        else:
            # Not enough data
            return {
                'is_bull': True,
                'reason': 'Insufficient data (default BULL)',
                'details': {},
                'regime': 'UNKNOWN'
            }

    except Exception as e:
        logger.error(f"WebSocket regime error: {e}")
        return {'error': str(e), 'regime': 'UNKNOWN', 'is_bull': True}

def broadcast_update(event_type, data):
    """Broadcast update to all connected clients"""
    with _clients_lock:  # v7.2: RC-2 guard — safe read of connected_clients across threads
        has_clients = bool(connected_clients)
    if has_clients:
        socketio.emit(event_type, convert_numpy_types(data))  # v6.45: Convert numpy types before emit


def _get_pending_trade_events():
    """v6.68: Read unnotified trade events from DB and mark them as notified."""
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'trade_history.db')
        db_path = os.path.normpath(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trade_events WHERE notified = 0 ORDER BY id"
            ).fetchall()
            if rows:
                ids = [r['id'] for r in rows]
                conn.execute(
                    f"UPDATE trade_events SET notified = 1 WHERE id IN ({','.join('?' * len(ids))})",
                    ids
                )
                conn.commit()
            return [dict(r) for r in rows]
    except Exception:
        return []


def background_monitor():
    """Background thread that monitors for changes and broadcasts updates"""
    global monitor_running

    last_positions = {}
    last_signals_count = 0
    last_regime = None
    first_position_load = True
    # v6.68: Two-speed loop — trade events every 2s, heavy checks every 10s
    trade_check_interval = 2   # seconds between trade_event checks
    heavy_check_every = 5      # run full position/signal/status check every N trade-check cycles
    heavy_counter = 0
    sync_counter = 0
    sync_interval = 15         # Sync with Alpaca every 15 heavy cycles (150s)

    logger.info("WebSocket background monitor started (v6.68: trade events every 2s)")

    while monitor_running:
        try:
            with _clients_lock:  # v7.2: RC-2 guard
                has_clients = bool(connected_clients)
            if has_clients:
                heavy_counter += 1

                # ── v6.68: Trade events check (every 2s) ──────────────────────
                pending = _get_pending_trade_events()
                if pending:
                    # v6.74: Invalidate status cache on trade — next browser poll gets fresh data
                    with _status_cache_lock:  # v7.2: RC-3 guard
                        _auto_status_cache['data'] = None
                    for ev in pending:
                        broadcast_update('trade_event', {
                            'type':     ev['event_type'],
                            'symbol':   ev['symbol'],
                            'price':    ev['price'],
                            'qty':      ev['qty'],
                            'pnl_pct':  ev.get('pnl_pct', 0),
                            'pnl_usd':  ev.get('pnl_usd', 0),
                            'strategy': ev.get('strategy', ''),
                            'reason':   ev.get('reason', ''),
                            'timestamp': ev['created_at'],
                        })
                    # Immediately refresh positions panel after a trade
                    positions_data = get_positions_data()
                    broadcast_update('positions_update', positions_data)
                    current_positions = {s['symbol']: s for s in positions_data.get('statuses', [])}
                    last_positions = current_positions.copy()
                    first_position_load = False

                # ── Heavy check (every 10s) ───────────────────────────────────
                if heavy_counter >= heavy_check_every:
                    heavy_counter = 0

                    # Periodically sync portfolio with Alpaca
                    sync_counter += 1
                    if sync_counter >= sync_interval:
                        sync_counter = 0
                        changes = sync_portfolio_with_alpaca()
                        if changes:
                            logger.info(f"Auto-synced {len(changes)} position changes from Alpaca")

                    # Check positions
                    positions_data = get_positions_data()
                    current_positions = {s['symbol']: s for s in positions_data.get('statuses', [])}

                    if current_positions != last_positions:
                        if first_position_load:
                            logger.info(f"Background monitor: first load, {len(current_positions)} existing positions (no trade events)")
                            broadcast_update('positions_update', positions_data)
                            last_positions = current_positions.copy()
                            first_position_load = False
                        else:
                            broadcast_update('positions_update', positions_data)
                            last_positions = current_positions.copy()

                    # Check signals
                    signals_data = get_signals_data()
                    if signals_data.get('count', 0) != last_signals_count:
                        broadcast_update('signals_update', signals_data)
                        last_signals_count = signals_data.get('count', 0)

                    # Regime + status
                    regime_data = get_regime_data()
                    broadcast_update('regime_update', regime_data)
                    if regime_data.get('regime') != last_regime:
                        last_regime = regime_data.get('regime')
                    broadcast_update('status_update', get_status_data())

            time.sleep(trade_check_interval)

        except Exception as e:
            logger.error(f"Background monitor error: {e}")
            time.sleep(5)

    logger.info("WebSocket background monitor stopped")

def start_monitor():
    """Start background monitor thread"""
    global monitor_thread, monitor_running

    if monitor_thread is None or not monitor_thread.is_alive():
        monitor_running = True
        monitor_thread = threading.Thread(target=background_monitor, daemon=True)
        monitor_thread.start()
        logger.info("Started WebSocket background monitor")

def stop_monitor():
    """Stop background monitor thread"""
    global monitor_running
    monitor_running = False
    logger.info("Stopping WebSocket background monitor")


def get_pdt_info():
    """Get PDT (Pattern Day Trader) info from Alpaca account with Smart Guard v2.0"""
    try:
        import requests
        headers = {
            "APCA-API-KEY-ID": os.getenv('ALPACA_API_KEY'),
            "APCA-API-SECRET-KEY": os.getenv('ALPACA_SECRET_KEY')
        }
        resp = requests.get("https://paper-api.alpaca.markets/v2/account", headers=headers)
        if resp.status_code == 200:
            account = resp.json()
            day_trade_count = int(account.get('daytrade_count', 0))
            day_trade_limit = 3
            remaining = max(0, day_trade_limit - day_trade_count)
            reserve = 1  # PDT Smart Guard reserve

            return {
                'day_trade_count': day_trade_count,
                'pdt_flag': account.get('pattern_day_trader', False),
                'day_trade_limit': day_trade_limit,
                'remaining': remaining,
                # PDT Smart Guard v2.0 additions
                'smart_guard': {
                    'version': '2.0',
                    'enabled': True,
                    'reserve': reserve,
                    'reserve_active': remaining <= reserve,
                    'sl_threshold': -2.5,
                    'tp_threshold': 4.0  # 4% for faster profit lock
                }
            }
    except Exception as e:
        logger.error(f"PDT info error: {e}")
    return {
        'day_trade_count': 0, 'pdt_flag': False, 'day_trade_limit': 3, 'remaining': 3,
        'smart_guard': {'version': '2.0', 'enabled': True, 'reserve': 1, 'reserve_active': False}
    }


def sync_portfolio_with_alpaca():
    """Sync rapid_portfolio.json with actual Alpaca positions"""
    try:
        import requests
        from rapid_portfolio_manager import RapidPortfolioManager

        headers = {
            "APCA-API-KEY-ID": os.getenv('ALPACA_API_KEY'),
            "APCA-API-SECRET-KEY": os.getenv('ALPACA_SECRET_KEY')
        }
        resp = requests.get("https://paper-api.alpaca.markets/v2/positions", headers=headers)
        alpaca_positions = resp.json()

        # Get current portfolio with broker (v4.7)
        from engine.brokers import AlpacaBroker
        broker = AlpacaBroker(paper=True)
        pm = RapidPortfolioManager(broker=broker)
        current_symbols = set(pm.positions.keys())
        alpaca_symbols = set(p['symbol'] for p in alpaca_positions)

        # Detect changes
        new_symbols = alpaca_symbols - current_symbols
        sold_symbols = current_symbols - alpaca_symbols

        changes = []

        # Remove sold positions
        for symbol in sold_symbols:
            if symbol in pm.positions:
                del pm.positions[symbol]
                changes.append(('SELL', symbol))
                logger.info(f"Portfolio sync: Removed {symbol} (sold)")

        # Add new positions
        for pos in alpaca_positions:
            symbol = pos['symbol']
            if symbol in new_symbols:
                entry_price = float(pos['avg_entry_price'])
                shares = int(pos['qty'])
                current_price = float(pos['current_price'])

                from rapid_portfolio_manager import Position
                pm.positions[symbol] = Position(
                    symbol=symbol,
                    entry_date=datetime.now().strftime("%Y-%m-%d"),
                    entry_price=entry_price,
                    shares=shares,
                    initial_stop_loss=entry_price * 0.975,
                    current_stop_loss=entry_price * 0.975,
                    take_profit=entry_price * 1.06,
                    cost_basis=entry_price * shares,
                    highest_price=current_price,
                    trailing_active=False,
                    initial_take_profit=entry_price * 1.06
                )
                changes.append(('BUY', symbol))
                logger.info(f"Portfolio sync: Added {symbol} - {shares} shares @ ${entry_price:.2f}")

        # Save if changes
        if changes:
            pm.save_portfolio()
            logger.info(f"Portfolio synced: {len(changes)} changes")

            # Broadcast changes via WebSocket
            for change_type, symbol in changes:
                broadcast_update('trade_event', {
                    'type': change_type,
                    'symbol': symbol,
                    'timestamp': datetime.now().isoformat()
                })

            # Broadcast updated positions
            broadcast_update('positions_update', get_positions_data())

        return changes

    except Exception as e:
        logger.error(f"Portfolio sync error: {e}")
        return []


def start_price_streamer():
    """Start Alpaca real-time price streamer"""
    try:
        from alpaca_streamer import init_streamer, get_streamer
        from rapid_portfolio_manager import RapidPortfolioManager

        # First sync portfolio with Alpaca
        sync_portfolio_with_alpaca()

        # Initialize streamer with socketio
        streamer = init_streamer(
            socketio=socketio,
            api_key=os.getenv('ALPACA_API_KEY'),
            secret_key=os.getenv('ALPACA_SECRET_KEY')
        )

        # Get current position symbols with broker (v4.7)
        from engine.brokers import AlpacaBroker
        broker = AlpacaBroker(paper=True)
        pm = RapidPortfolioManager(broker=broker)
        symbols = list(pm.positions.keys())

        if symbols:
            # Subscribe to position symbols (trades only - bars not available on IEX)
            streamer.subscribe(symbols, trades=True, bars=False)
            streamer.start()
            logger.info(f"Price streamer started for: {symbols}")
        else:
            logger.info("No positions to stream prices for")

        return streamer

    except Exception as e:
        logger.error(f"Failed to start price streamer: {e}")
        return None


# API endpoint to manually sync portfolio with Alpaca
@app.route('/api/rapid/sync', methods=['POST'])
def api_rapid_sync():
    """Manually sync portfolio with Alpaca positions"""
    try:
        changes = sync_portfolio_with_alpaca()
        return jsonify({
            'success': True,
            'changes': [{'type': c[0], 'symbol': c[1]} for c in changes],
            'message': f'Synced {len(changes)} changes'
        })
    except Exception as e:
        logger.error(f"Manual sync error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# TRADE LOG API v1.0
# ============================================================

@app.route('/api/trade-logs')
def api_trade_logs():
    """
    Get today's trade logs and summary for UI display.

    v6.81: Read directly from SQLite trades table (engine + webapp same DB).
    Previously used in-memory TradeLogger which only saw webapp-process logs,
    missing all engine SKIPs (different process, different singleton).
    """
    try:
        import sqlite3
        import pytz
        et_tz = pytz.timezone('America/New_York')
        today = datetime.now(et_tz).strftime('%Y-%m-%d')

        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'trade_history.db')
        db_path = os.path.normpath(db_path)

        with sqlite3.connect(db_path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM trades WHERE date = ? ORDER BY timestamp DESC LIMIT 100",
                (today,)
            )
            rows = cur.fetchall()

        logs = []
        for row in rows:
            full = json.loads(row['full_data']) if row['full_data'] else {}
            logs.append({
                'id': row['id'],
                'timestamp': row['timestamp'],
                'action': row['action'],
                'symbol': row['symbol'],
                'qty': row['qty'],
                'price': row['price'],
                'reason': row['reason'],
                'pnl_usd': row['pnl_usd'],
                'pnl_pct': row['pnl_pct'],
                'hold_duration': row['hold_duration'],
                'mode': row['mode'],
                'from_queue': bool(row['from_queue']),
                'signal_score': row['signal_score'],
                # Extra fields from full_data (not in columns)
                'skip_reason': full.get('skip_reason'),
                'entry_rsi': full.get('entry_rsi'),
                'momentum_5d': full.get('momentum_5d'),
            })

        buys = [l for l in logs if l['action'] == 'BUY']
        sells = [l for l in logs if l['action'] == 'SELL']
        skips = [l for l in logs if l['action'] == 'SKIP']
        winners = [l for l in sells if (l['pnl_usd'] or 0) > 0]
        losers = [l for l in sells if (l['pnl_usd'] or 0) <= 0]
        total_pnl = sum(l['pnl_usd'] or 0 for l in sells)

        summary = {
            'date': today,
            'total_trades': len(buys) + len(sells),
            'buys': len(buys),
            'sells': len(sells),
            'skips': len(skips),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': round(len(winners) / len(sells) * 100, 1) if sells else 0,
            'total_pnl_usd': round(total_pnl, 2),
            'low_risk_trades': sum(1 for l in logs if l.get('mode') == 'LOW_RISK'),
            'pdt_used': len(buys),
            'queue_trades': sum(1 for l in logs if l.get('from_queue')),
        }

        return jsonify({
            'summary': summary,
            'logs': logs,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Trade logs error: {e}")
        return jsonify({
            'summary': {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'total_trades': 0,
                'buys': 0,
                'sells': 0,
                'skips': 0,
                'winners': 0,
                'losers': 0,
                'win_rate': 0,
                'total_pnl_usd': 0
            },
            'logs': [],
            'error': str(e)
        }), 500


@app.route('/api/trade-logs/history')
def api_trade_logs_history():
    """
    Query historical trade logs

    Query params:
        start_date: YYYY-MM-DD (optional)
        end_date: YYYY-MM-DD (optional)
        symbol: Filter by symbol (optional)
        action: BUY, SELL, or SKIP (optional)
        limit: Max results (default 100)
    """
    try:
        from trade_logger import get_trade_logger

        trade_logger = get_trade_logger()

        # Get query params
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        symbol = request.args.get('symbol')
        action = request.args.get('action')
        limit = int(request.args.get('limit', 100))

        # Query history
        logs = trade_logger.query_history(
            start_date=start_date,
            end_date=end_date,
            symbol=symbol,
            action=action,
            limit=limit
        )

        return jsonify({
            'count': len(logs),
            'logs': logs,
            'query': {
                'start_date': start_date,
                'end_date': end_date,
                'symbol': symbol,
                'action': action,
                'limit': limit
            }
        })

    except Exception as e:
        logger.error(f"Trade logs history error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/trade-logs/stats')
def api_trade_logs_stats():
    """
    Get performance statistics

    Query params:
        days: Number of days to analyze (default 30)
    """
    try:
        from trade_logger import get_trade_logger

        trade_logger = get_trade_logger()
        days = int(request.args.get('days', 30))

        stats = trade_logger.get_performance_stats(days=days)

        return jsonify({
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Trade logs stats error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# TRADE ANALYTICS DASHBOARD v1.0
# ============================================================

@app.route('/analytics')
def analytics_page():
    """Trade Performance Dashboard"""
    return render_template('analytics.html')


@app.route('/api/analytics')
def api_analytics():
    """Comprehensive analytics data for dashboard"""
    try:
        from trade_logger import get_trade_logger

        trade_logger = get_trade_logger()
        days = int(request.args.get('days', 30))

        analytics = trade_logger.get_analytics(days=days)
        analytics['timestamp'] = datetime.now().isoformat()

        return jsonify(analytics)

    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return jsonify({'error': str(e)}), 500


# API endpoint to subscribe to new symbols
@app.route('/api/stream/subscribe', methods=['POST'])
def api_stream_subscribe():
    """Subscribe to real-time prices for symbols"""
    try:
        from alpaca_streamer import get_streamer

        data = request.get_json()
        symbols = data.get('symbols', [])

        streamer = get_streamer()
        if streamer:
            streamer.subscribe(symbols)
            return jsonify({'success': True, 'symbols': symbols})
        else:
            return jsonify({'error': 'Streamer not running'}), 503

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stream/prices')
def api_stream_prices():
    """Get all cached real-time prices"""
    try:
        from alpaca_streamer import get_streamer

        streamer = get_streamer()
        if streamer:
            return jsonify({
                'prices': streamer.get_all_prices(),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Streamer not running'}), 503

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# ALERTS API v1.0
# ============================================================

@app.route('/api/alerts')
def api_alerts():
    """
    Get recent alerts for Rapid Trader page.

    Query params:
        limit: Max alerts (default 50)
        level: Filter by level (CRITICAL, WARNING, INFO)
        category: Filter by category (trade, system, health, regime)
        unack: If 'true', only unacknowledged alerts
    """
    try:
        from alert_manager import get_alert_manager

        mgr = get_alert_manager()

        limit = int(request.args.get('limit', 50))
        level = request.args.get('level')
        category = request.args.get('category')
        unack = request.args.get('unack', '').lower() == 'true'

        alerts = mgr.get_recent(
            limit=limit,
            level=level,
            category=category,
            unacknowledged_only=unack,
        )
        summary = mgr.get_summary()

        return jsonify({
            'alerts': alerts,
            'summary': summary,
            'timestamp': datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Alerts API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/acknowledge', methods=['POST'])
def api_alerts_acknowledge():
    """Acknowledge one or all alerts."""
    try:
        from alert_manager import get_alert_manager

        mgr = get_alert_manager()
        data = request.get_json() or {}
        alert_id = data.get('id')

        if alert_id == 'all' or alert_id is None:
            count = mgr.acknowledge_all()
            return jsonify({'success': True, 'acknowledged': count})
        else:
            ok = mgr.acknowledge(int(alert_id))
            return jsonify({'success': ok})

    except Exception as e:
        logger.error(f"Alert acknowledge error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/reload', methods=['POST'])
@require_api_auth
def api_config_reload():
    """
    Hot-reload trading config from YAML file.

    v6.10: Uses RapidRotationConfig instead of trading_config.py
    """
    try:
        from config.strategy_config import RapidRotationConfig
        import os

        # Find config file path
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'trading.yaml'
        )

        # Load new config from YAML
        new_config = RapidRotationConfig.from_yaml(config_path)

        engine = get_auto_trading_engine()
        if engine:
            # Update engine's config
            engine._core_config = new_config
            # Reload all parameters from new config
            engine._load_config_from_yaml()

            param_count = len(new_config.__dataclass_fields__)
            logger.info(f"✅ Config reloaded: {param_count} parameters from RapidRotationConfig")
            # v6.41: Get version from engine (single source of truth)
            engine_version = engine.get_status().get('version', APP_VERSION) if engine else APP_VERSION
            return jsonify({
                'success': True,
                'params': param_count,
                'version': engine_version,
                'source': 'RapidRotationConfig'
            })
        else:
            param_count = len(new_config.__dataclass_fields__)
            return jsonify({
                'success': True,
                'params': param_count,
                'note': 'Engine not running',
                'version': 'v6.10'
            })

    except Exception as e:
        logger.error(f"Config reload error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/summary')
def api_alerts_summary():
    """Get alert count summary (lightweight, for polling)."""
    try:
        from alert_manager import get_alert_manager

        mgr = get_alert_manager()
        return jsonify(mgr.get_summary())

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# ============================================================================
# DATABASE API (Phase 3: Data Access Layer Integration)
# ============================================================================

@app.route('/api/db/trades/recent')
def api_db_trades_recent():
    """Get recent trades using TradeRepository."""
    try:
        from database import TradeRepository

        days = request.args.get('days', 7, type=int)
        limit = request.args.get('limit', 100, type=int)

        repo = TradeRepository()
        trades = repo.get_recent_trades(days=days, limit=limit)

        return jsonify({
            'success': True,
            'count': len(trades),
            'trades': [t.to_dict() for t in trades]
        })

    except Exception as e:
        logger.error(f"Failed to get recent trades: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/trades/stats')
def api_db_trades_stats():
    """Get trade statistics using TradeRepository."""
    try:
        from database import TradeRepository
        from datetime import date, timedelta

        days = request.args.get('days', 30, type=int)

        repo = TradeRepository()

        # Get stats for last N days
        start_date = date.today() - timedelta(days=days)
        stats = repo.get_statistics(start_date=start_date)

        # Get all-time stats
        all_time_stats = repo.get_statistics()

        return jsonify({
            'success': True,
            'period_days': days,
            'period_stats': stats,
            'all_time_stats': all_time_stats
        })

    except Exception as e:
        logger.error(f"Failed to get trade stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/trades/symbol/<symbol>')
def api_db_trades_by_symbol(symbol):
    """Get trades for specific symbol using TradeRepository."""
    try:
        from database import TradeRepository

        limit = request.args.get('limit', 50, type=int)

        repo = TradeRepository()
        trades = repo.get_by_symbol(symbol.upper(), limit=limit)

        return jsonify({
            'success': True,
            'symbol': symbol.upper(),
            'count': len(trades),
            'trades': [t.to_dict() for t in trades]
        })

    except Exception as e:
        logger.error(f"Failed to get trades for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/positions')
def api_db_positions():
    """Get active positions using PositionRepository."""
    try:
        from database import PositionRepository

        repo = PositionRepository()
        positions = repo.get_all()

        # Calculate total exposure
        total_exposure = repo.get_total_exposure()

        return jsonify({
            'success': True,
            'count': len(positions),
            'total_exposure': total_exposure,
            'positions': [p.to_dict() for p in positions]
        })

    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/prices/<symbol>')
def api_db_prices(symbol):
    """Get price history using StockDataRepository."""
    try:
        from database import StockDataRepository

        days = request.args.get('days', 30, type=int)

        repo = StockDataRepository()

        # Get latest price
        latest = repo.get_latest_price(symbol.upper())

        # Get price history
        prices = repo.get_prices(symbol.upper(), days=days)

        return jsonify({
            'success': True,
            'symbol': symbol.upper(),
            'latest': latest.to_dict() if latest else None,
            'history_count': len(prices),
            'history': [p.to_dict() for p in prices[:100]]  # Limit to 100 for response size
        })

    except Exception as e:
        logger.error(f"Failed to get prices for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/db/stats')
def api_db_stats():
    """Get database statistics."""
    try:
        from database import TradeRepository, PositionRepository, StockDataRepository

        trade_repo = TradeRepository()
        position_repo = PositionRepository()
        stock_repo = StockDataRepository()

        # Get counts
        stats = {
            'trades': {
                'total': trade_repo.get_statistics().get('total_trades', 0),
                'open': len(trade_repo.get_open_trades()),
                'recent_7d': len(trade_repo.get_recent_trades(days=7))
            },
            'positions': {
                'count': position_repo.count(),
                'exposure': position_repo.get_total_exposure(),
                'symbols': position_repo.get_symbols()
            },
            'stock_data': {
                'symbols': stock_repo.get_symbols_count(),
                'prices': stock_repo.get_price_count()
            }
        }

        return jsonify({
            'success': True,
            'stats': stats
        })

    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Load environment variables from .env file (v4.7)
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    load_dotenv(env_path)
    logger.info(f"Loaded .env from: {env_path}")
    logger.info(f"Alpaca API key configured: {bool(os.getenv('ALPACA_API_KEY'))}")

    # Start background monitor
    start_monitor()

    # Start Alpaca real-time price streamer
    start_price_streamer()

    # Use socketio.run instead of app.run for WebSocket support
    # v6.51: eventlet handles WebSocket natively — no allow_unsafe_werkzeug needed
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
