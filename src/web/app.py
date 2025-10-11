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
from utils import clean_analysis_results
from symbol_utils import SymbolUtils
from screeners.support_level_screener import SupportLevelScreener
from screeners.dividend_screener import DividendGrowthScreener
from screeners.value_screener import ValueStockScreener
from ai_market_analyst import AIMarketAnalyst
from analysis.fundamental.earnings_analyst import EarningsAnalystAnalyzer


app = Flask(__name__)
CORS(app)

# Initialize stock analyzer and screeners (now AI-only)
analyzer = StockAnalyzer()
support_screener = SupportLevelScreener(analyzer)
dividend_screener = DividendGrowthScreener(analyzer)
value_screener = ValueStockScreener(analyzer)
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

        # Add ETF information
        etf_info = SymbolUtils.get_etf_info(symbol)
        if etf_info:
            results['etf_info'] = etf_info

        # Clean results for JSON serialization
        cleaned_results = clean_analysis_results(results)

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
        max_stocks = data.get('max_stocks', 10)
        time_horizon = data.get('time_horizon', 'medium')

        # Run support level screening
        opportunities = support_screener.screen_support_opportunities(
            max_distance_from_support=max_distance_from_support,
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
            'total_screened': "AI-generated universe",
            'found_opportunities': len(opportunities),
            'criteria': {
                'max_distance_from_support': max_distance_from_support,
                'min_fundamental_score': min_fundamental_score,
                'min_technical_score': min_technical_score,
                'max_stocks': max_stocks,
                'time_horizon': time_horizon
            }
        })

    except Exception as e:
        logger.error(f"Support screening API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chart-data/<symbol>')
def api_chart_data(symbol):
    """API endpoint for chart data"""
    try:
        # Get price data for charts
        price_data = analyzer.data_manager.get_price_data(symbol.upper(), period='1y')

        if price_data is None or price_data.empty:
            return jsonify({'error': 'No price data available'}), 404

        # Convert to chart format
        price_data = price_data.tail(252)  # Last year of trading days

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
        max_stocks = data.get('max_stocks', 10)
        time_horizon = data.get('time_horizon', 'medium')

        logger.info(f"🤖 Starting AI-powered support level screening with {max_stocks} target stocks")

        # Run AI-powered support level screening
        opportunities = support_screener.screen_support_opportunities(
            max_distance_from_support=max_distance_from_support,
            min_fundamental_score=min_fundamental_score,
            min_technical_score=min_technical_score,
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

        # Extract criteria
        min_volatility = data.get('min_volatility', 30.0)
        min_avg_volume = data.get('min_avg_volume', 1000000)
        min_price_range = data.get('min_price_range', 5.0)
        min_momentum_score = data.get('min_momentum_score', 4.0)
        max_stocks = data.get('max_stocks', 20)
        time_horizon = data.get('time_horizon', 'short')

        logger.info(f"🚀 Starting volatile trading screening with {max_stocks} target stocks")

        # Run volatile trading screening
        opportunities = value_screener.screen_volatile_trading_opportunities(
            min_volatility=min_volatility,
            min_avg_volume=min_avg_volume,
            min_price_range=min_price_range,
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)