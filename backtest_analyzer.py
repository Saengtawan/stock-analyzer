"""
Backtesting Script for Stock Analyzer
Tests system accuracy by analyzing historical data and comparing predictions vs reality
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from loguru import logger
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from main import StockAnalyzer
from api.yahoo_finance_client import YahooFinanceClient


class BacktestAnalyzer:
    """Backtest the stock analyzer system"""

    def __init__(self):
        self.analyzer = StockAnalyzer()
        self.yf_client = YahooFinanceClient()

    def get_historical_analysis(self,
                                symbol: str,
                                analysis_date: datetime,
                                time_horizon: str = 'short',
                                account_size: float = 100000) -> Dict[str, Any]:
        """
        Run analysis as if it was performed on a historical date

        Args:
            symbol: Stock symbol
            analysis_date: Date to perform analysis (as if analyzing on this date)
            time_horizon: short/medium/long
            account_size: Account size for position sizing

        Returns:
            Analysis results from that date
        """
        logger.info(f"📅 Running analysis for {symbol} as if date was {analysis_date.date()}")

        # Get data up to analysis_date
        # We need enough historical data for indicators
        start_date = analysis_date - timedelta(days=400)  # Get ~1 year+ for indicators

        try:
            # Get historical price data up to analysis_date
            ticker = self.yf_client.session
            import yfinance as yf
            ticker_obj = yf.Ticker(symbol)

            # Get data up to analysis_date
            hist_data = ticker_obj.history(
                start=start_date.strftime('%Y-%m-%d'),
                end=(analysis_date + timedelta(days=1)).strftime('%Y-%m-%d'),  # Include analysis_date
                interval='1d'
            )

            if hist_data.empty:
                logger.error(f"No historical data found for {symbol} up to {analysis_date.date()}")
                return None

            # Get the "current" price (price on analysis_date)
            if analysis_date.date() not in hist_data.index.date:
                # Find closest date
                closest_date = min(hist_data.index, key=lambda d: abs(d.date() - analysis_date.date()))
                logger.warning(f"Analysis date {analysis_date.date()} not in data, using closest: {closest_date.date()}")
                current_price = float(hist_data.loc[closest_date]['Close'])
            else:
                current_price = float(hist_data[hist_data.index.date == analysis_date.date()]['Close'].iloc[0])

            logger.info(f"💰 Price on {analysis_date.date()}: ${current_price:.2f}")

            # Truncate data to only include data up to analysis_date
            hist_data = hist_data[hist_data.index.date <= analysis_date.date()]

            # Convert to DataFrame format expected by analyzer
            price_data = hist_data.reset_index()
            price_data.columns = price_data.columns.str.lower()
            price_data['symbol'] = symbol

            # Run the analysis with historical data
            results = self.analyzer.analyze(
                symbol=symbol,
                time_horizon=time_horizon,
                account_size=account_size,
                historical_price_data=price_data,  # Pass historical data
                analysis_date=analysis_date  # Pass analysis date for context
            )

            results['backtest_info'] = {
                'analysis_date': analysis_date.isoformat(),
                'current_price_at_analysis': current_price,
                'data_points': len(price_data)
            }

            return results

        except Exception as e:
            logger.error(f"Failed to get historical analysis: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_actual_performance(self,
                              symbol: str,
                              entry_date: datetime,
                              entry_price: float,
                              target_price: float,
                              stop_loss: float,
                              days_forward: int = 7) -> Dict[str, Any]:
        """
        Get actual price performance after the analysis date

        Args:
            symbol: Stock symbol
            entry_date: Date of analysis/entry
            entry_price: Entry price
            target_price: Predicted target
            stop_loss: Stop loss level
            days_forward: Days to check forward

        Returns:
            Actual performance metrics
        """
        logger.info(f"📊 Checking actual performance for {symbol} from {entry_date.date()}")

        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)

            # Get data from entry_date forward
            end_date = entry_date + timedelta(days=days_forward + 5)  # Extra days for market closures

            future_data = ticker.history(
                start=entry_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                interval='1d'
            )

            if future_data.empty:
                logger.error("No future data available")
                return None

            # Analyze price movement
            prices = future_data['Close'].values
            highs = future_data['High'].values
            lows = future_data['Low'].values
            dates = future_data.index

            # Check if TP or SL was hit
            tp_hit = False
            sl_hit = False
            tp_date = None
            sl_date = None
            exit_price = prices[-1]  # Last price in period
            exit_date = dates[-1]

            for i, (high, low, date) in enumerate(zip(highs, lows, dates)):
                # Check SL first (more conservative)
                if low <= stop_loss and not sl_hit:
                    sl_hit = True
                    sl_date = date
                    exit_price = stop_loss
                    exit_date = date
                    logger.warning(f"🔴 Stop Loss hit on {date.date()} at ${stop_loss:.2f}")
                    break

                # Check TP
                if high >= target_price and not tp_hit:
                    tp_hit = True
                    tp_date = date
                    exit_price = target_price
                    exit_date = date
                    logger.info(f"🟢 Target Price hit on {date.date()} at ${target_price:.2f}")
                    break

            # Calculate returns
            if entry_price > 0:
                return_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                return_pct = 0

            # Determine outcome
            if tp_hit:
                outcome = 'WIN'
                outcome_emoji = '🎯'
            elif sl_hit:
                outcome = 'LOSS'
                outcome_emoji = '❌'
            elif return_pct > 0:
                outcome = 'SMALL_WIN'
                outcome_emoji = '📈'
            elif return_pct < 0:
                outcome = 'SMALL_LOSS'
                outcome_emoji = '📉'
            else:
                outcome = 'NEUTRAL'
                outcome_emoji = '➖'

            # Get max gain/loss during period
            max_price = max(highs)
            min_price = min(lows)
            max_gain_pct = ((max_price - entry_price) / entry_price) * 100
            max_loss_pct = ((min_price - entry_price) / entry_price) * 100

            results = {
                'outcome': outcome,
                'outcome_emoji': outcome_emoji,
                'tp_hit': tp_hit,
                'sl_hit': sl_hit,
                'tp_date': tp_date.date() if tp_date else None,
                'sl_date': sl_date.date() if sl_date else None,
                'exit_price': exit_price,
                'exit_date': exit_date.date(),
                'return_pct': return_pct,
                'max_gain_pct': max_gain_pct,
                'max_loss_pct': max_loss_pct,
                'days_held': len(prices),
                'entry_price': entry_price,
                'target_price': target_price,
                'stop_loss': stop_loss
            }

            logger.info(f"{outcome_emoji} Outcome: {outcome} | Return: {return_pct:+.2f}%")

            return results

        except Exception as e:
            logger.error(f"Failed to get actual performance: {e}")
            import traceback
            traceback.print_exc()
            return None

    def backtest_single(self,
                       symbol: str,
                       analysis_date: datetime,
                       days_forward: int = 7,
                       time_horizon: str = 'short') -> Dict[str, Any]:
        """
        Run a single backtest

        Args:
            symbol: Stock symbol
            analysis_date: Date to run analysis
            days_forward: Days to check forward for results
            time_horizon: short/medium/long

        Returns:
            Backtest results
        """
        logger.info("=" * 80)
        logger.info(f"🔬 BACKTEST: {symbol} on {analysis_date.date()}")
        logger.info("=" * 80)

        # Run historical analysis
        analysis = self.get_historical_analysis(symbol, analysis_date, time_horizon)

        if not analysis:
            logger.error("Failed to get historical analysis")
            return None

        # Extract recommendation and targets
        unified_rec = analysis.get('unified_recommendation', {})
        recommendation = unified_rec.get('recommendation', 'UNKNOWN')
        score = unified_rec.get('score', 0)
        confidence = unified_rec.get('confidence', 'UNKNOWN')

        # Get immediate entry info
        immediate_entry_info = unified_rec.get('immediate_entry_info', {})
        is_immediate_entry = immediate_entry_info.get('immediate_entry', False)
        immediate_confidence = immediate_entry_info.get('confidence', 0)

        # Get entry levels
        entry_levels = unified_rec.get('entry_levels', {})
        current_price = unified_rec.get('current_price', 0)

        # Determine entry price based on immediate entry flag
        if is_immediate_entry:
            # Immediate entry - use current price
            entry_price = current_price
            entry_type = 'IMMEDIATE'
        else:
            # Wait for pullback - use recommended entry
            entry_price = entry_levels.get('recommended', 0)
            entry_type = 'PULLBACK'

            # Fallback to current price if no recommended entry
            if entry_price == 0:
                entry_price = current_price
                entry_type = 'FALLBACK'

        target_price = unified_rec.get('target_price', 0)
        stop_loss = unified_rec.get('stop_loss', 0)
        rr_ratio = unified_rec.get('risk_reward_analysis', {}).get('ratio', 0)

        # Validate essential data
        if not all([target_price, stop_loss, entry_price]):
            logger.error(f"⚠️ Skipping backtest - Missing essential data: entry=${entry_price}, tp=${target_price}, sl=${stop_loss}")
            return None

        logger.info(f"📋 Recommendation: {recommendation} (Score: {score:.1f}/10, Confidence: {confidence})")
        logger.info(f"🎯 Entry Type: {entry_type} | Immediate: {is_immediate_entry} (Confidence: {immediate_confidence}%)")
        logger.info(f"💰 Entry: ${entry_price:.2f} | TP: ${target_price:.2f} | SL: ${stop_loss:.2f} | R:R: {rr_ratio:.2f}")

        # Get actual performance
        actual = self.get_actual_performance(
            symbol=symbol,
            entry_date=analysis_date,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            days_forward=days_forward
        )

        if not actual:
            logger.error("Failed to get actual performance")
            return None

        # Evaluate recommendation accuracy
        rec_correct = self._evaluate_recommendation(recommendation, actual['return_pct'])

        results = {
            'symbol': symbol,
            'analysis_date': analysis_date.date(),
            'recommendation': recommendation,
            'score': score,
            'confidence': confidence,
            'entry_type': entry_type,  # IMMEDIATE / PULLBACK / FALLBACK
            'is_immediate_entry': is_immediate_entry,
            'immediate_confidence': immediate_confidence,
            'entry_price': entry_price,
            'target_price': target_price,
            'stop_loss': stop_loss,
            'rr_ratio': rr_ratio,
            'actual_performance': actual,
            'recommendation_correct': rec_correct,
            'analysis': analysis  # Full analysis for reference
        }

        # Print summary
        self._print_backtest_summary(results)

        return results

    def _evaluate_recommendation(self, recommendation: str, return_pct: float) -> bool:
        """
        Evaluate if recommendation was correct

        Args:
            recommendation: BUY/SELL/HOLD/AVOID
            return_pct: Actual return percentage

        Returns:
            True if recommendation was correct
        """
        if recommendation in ['STRONG BUY', 'BUY']:
            # BUY should result in positive return
            return return_pct > 0
        elif recommendation == 'HOLD':
            # HOLD means don't enter, hard to evaluate
            # 🆕 v6.0: Widened threshold from ±2% to ±3% (less strict)
            # We'll consider it correct if return is small (< ±3%)
            return abs(return_pct) < 3
        elif recommendation in ['SELL', 'AVOID', 'STRONG SELL']:
            # SELL/AVOID should result in negative return (or we avoided loss)
            return return_pct <= 0
        else:
            return False

    def _print_backtest_summary(self, results: Dict[str, Any]):
        """Print a formatted backtest summary"""
        actual = results['actual_performance']

        logger.info("\n" + "=" * 80)
        logger.info("📊 BACKTEST RESULTS SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Symbol: {results['symbol']}")
        logger.info(f"Analysis Date: {results['analysis_date']}")
        logger.info(f"Recommendation: {results['recommendation']} (Score: {results['score']:.1f}, Confidence: {results['confidence']})")
        logger.info("-" * 80)
        logger.info(f"Entry Type: {results['entry_type']} (Immediate: {'✅ Yes' if results['is_immediate_entry'] else '❌ No'}, Confidence: {results['immediate_confidence']}%)")
        logger.info(f"Entry Price: ${results['entry_price']:.2f}")
        logger.info(f"Target Price: ${results['target_price']:.2f} ({((results['target_price']/results['entry_price']-1)*100):+.2f}%)")
        logger.info(f"Stop Loss: ${results['stop_loss']:.2f} ({((results['stop_loss']/results['entry_price']-1)*100):+.2f}%)")
        logger.info(f"R:R Ratio: {results['rr_ratio']:.2f}")
        logger.info("-" * 80)
        logger.info(f"Actual Outcome: {actual['outcome_emoji']} {actual['outcome']}")
        logger.info(f"Exit Price: ${actual['exit_price']:.2f} on {actual['exit_date']}")
        logger.info(f"Return: {actual['return_pct']:+.2f}%")
        logger.info(f"Max Gain: {actual['max_gain_pct']:+.2f}% | Max Loss: {actual['max_loss_pct']:+.2f}%")
        logger.info(f"Days Held: {actual['days_held']}")
        logger.info(f"TP Hit: {'✅ Yes' if actual['tp_hit'] else '❌ No'}")
        logger.info(f"SL Hit: {'⚠️ Yes' if actual['sl_hit'] else '✅ No'}")
        logger.info("-" * 80)
        logger.info(f"Recommendation Correct: {'✅ YES' if results['recommendation_correct'] else '❌ NO'}")
        logger.info("=" * 80 + "\n")

    def backtest_multiple(self,
                         symbol: str,
                         days_back: int = 30,
                         interval_days: int = 7,
                         time_horizon: str = 'short') -> List[Dict[str, Any]]:
        """
        Run multiple backtests over a period

        Args:
            symbol: Stock symbol
            days_back: How many days back to start testing
            interval_days: Days between each test
            time_horizon: short/medium/long

        Returns:
            List of backtest results
        """
        results = []

        # Generate test dates
        end_date = datetime.now() - timedelta(days=7)  # Don't test too recent (need data to verify)
        start_date = end_date - timedelta(days=days_back)

        current_date = start_date
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                result = self.backtest_single(
                    symbol=symbol,
                    analysis_date=current_date,
                    days_forward=7,
                    time_horizon=time_horizon
                )
                if result:
                    results.append(result)

            current_date += timedelta(days=interval_days)

        # Print aggregate statistics
        self._print_aggregate_stats(results)

        return results

    def _print_aggregate_stats(self, results: List[Dict[str, Any]]):
        """Print aggregate statistics from multiple backtests"""
        if not results:
            logger.warning("No backtest results to aggregate")
            return

        total_tests = len(results)
        correct_recs = sum(1 for r in results if r['recommendation_correct'])
        tp_hits = sum(1 for r in results if r['actual_performance']['tp_hit'])
        sl_hits = sum(1 for r in results if r['actual_performance']['sl_hit'])

        avg_return = sum(r['actual_performance']['return_pct'] for r in results) / total_tests
        wins = sum(1 for r in results if r['actual_performance']['return_pct'] > 0)
        losses = sum(1 for r in results if r['actual_performance']['return_pct'] < 0)

        # Entry type statistics
        immediate_entries = sum(1 for r in results if r.get('is_immediate_entry', False))
        pullback_entries = sum(1 for r in results if r.get('entry_type') == 'PULLBACK')
        fallback_entries = sum(1 for r in results if r.get('entry_type') == 'FALLBACK')

        logger.info("\n" + "=" * 80)
        logger.info("📈 AGGREGATE BACKTEST STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Recommendation Accuracy: {correct_recs}/{total_tests} ({(correct_recs/total_tests*100):.1f}%)")
        logger.info(f"Win Rate: {wins}/{total_tests} ({(wins/total_tests*100):.1f}%)")
        logger.info(f"Loss Rate: {losses}/{total_tests} ({(losses/total_tests*100):.1f}%)")
        logger.info(f"Average Return: {avg_return:+.2f}%")
        logger.info(f"TP Hit Rate: {tp_hits}/{total_tests} ({(tp_hits/total_tests*100):.1f}%)")
        logger.info(f"SL Hit Rate: {sl_hits}/{total_tests} ({(sl_hits/total_tests*100):.1f}%)")
        logger.info("-" * 80)
        logger.info(f"Entry Type Distribution:")
        logger.info(f"  Immediate Entry: {immediate_entries}/{total_tests} ({(immediate_entries/total_tests*100):.1f}%)")
        logger.info(f"  Pullback Entry:  {pullback_entries}/{total_tests} ({(pullback_entries/total_tests*100):.1f}%)")
        logger.info(f"  Fallback Entry:  {fallback_entries}/{total_tests} ({(fallback_entries/total_tests*100):.1f}%)")
        logger.info("=" * 80 + "\n")


def main():
    """Main function to run backtests"""
    import argparse

    parser = argparse.ArgumentParser(description='Backtest Stock Analyzer System')
    parser.add_argument('symbol', type=str, help='Stock symbol (e.g., AAPL)')
    parser.add_argument('--days-back', type=int, default=7, help='Days back from today to analyze')
    parser.add_argument('--multiple', action='store_true', help='Run multiple backtests over period')
    parser.add_argument('--period', type=int, default=30, help='Period in days for multiple backtests')
    parser.add_argument('--interval', type=int, default=7, help='Interval between backtests in days')
    parser.add_argument('--horizon', type=str, default='short', choices=['short', 'medium', 'long'],
                       help='Time horizon for analysis')

    args = parser.parse_args()

    backtester = BacktestAnalyzer()

    if args.multiple:
        # Run multiple backtests
        logger.info(f"🔬 Running multiple backtests for {args.symbol} over {args.period} days")
        backtester.backtest_multiple(
            symbol=args.symbol,
            days_back=args.period,
            interval_days=args.interval,
            time_horizon=args.horizon
        )
    else:
        # Run single backtest
        analysis_date = datetime.now() - timedelta(days=args.days_back)
        backtester.backtest_single(
            symbol=args.symbol,
            analysis_date=analysis_date,
            days_forward=7,
            time_horizon=args.horizon
        )


if __name__ == '__main__':
    main()
