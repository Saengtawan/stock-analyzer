#!/usr/bin/env python3
"""
Test script to verify backtest calculation fixes
"""
import sys
import pandas as pd
from main import StockAnalyzer

def test_backtest_fixes():
    """Test the backtest engine with QQQ data"""
    print("Testing backtest calculation fixes...")

    # Initialize analyzer
    analyzer = StockAnalyzer()

    # Run backtest on QQQ
    symbols = ['QQQ']
    start_date = '2022-01-01'
    end_date = '2024-01-01'
    initial_capital = 100000

    print(f"Running backtest: {symbols} from {start_date} to {end_date}")
    print(f"Initial capital: ${initial_capital:,.2f}")

    try:
        results = analyzer.run_backtest(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital
        )

        if 'error' in results:
            print(f"❌ Backtest failed: {results['error']}")
            return False

        # Extract key metrics
        performance = results.get('performance_metrics', {})
        trades = results.get('trades', [])

        print("\n📊 Performance Metrics:")
        print(f"Total Return: {performance.get('total_return', 0):.2f}%")
        print(f"Annualized Return: {performance.get('annualized_return', 0):.2f}%")
        print(f"Max Drawdown: {performance.get('max_drawdown', 0):.2f}%")
        print(f"Win Rate: {performance.get('win_rate', 0):.2f}%")
        print(f"Total Trades: {performance.get('total_trades', 0)}")
        print(f"Sharpe Ratio: {performance.get('sharpe_ratio', 0):.2f}")

        print(f"\n💰 Portfolio Summary:")
        portfolio_summary = results.get('portfolio_summary', {})
        print(f"Initial Capital: ${portfolio_summary.get('initial_capital', 0):,.2f}")
        print(f"Final Value: ${portfolio_summary.get('current_value', 0):,.2f}")

        print(f"\n📈 Trade Analysis:")
        if trades:
            print(f"First 3 trades:")
            for i, trade in enumerate(trades[:3]):
                print(f"  Trade {i+1}: {trade.get('action')} {trade.get('symbol')} "
                      f"on {trade.get('date')} - Price: ${trade.get('price', 0):.2f}, "
                      f"Shares: {trade.get('shares', 0)}, Value: ${trade.get('value', 0):.2f}")
                if 'pnl' in trade:
                    print(f"    P&L: ${trade.get('pnl', 0):.2f}")
        else:
            print("  No trades executed")

        print("\n✅ Backtest completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_backtest_fixes()
    sys.exit(0 if success else 1)