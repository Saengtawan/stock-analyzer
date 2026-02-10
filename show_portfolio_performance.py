#!/usr/bin/env python3
"""
PORTFOLIO PERFORMANCE REPORT

แสดง equity curve, performance metrics จาก Alpaca
พร้อม visualization แบบ ASCII art

Usage:
    python show_portfolio_performance.py [period]

    period: 1D, 1W, 1M, 3M, 1A, all (default: 1M)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from engine.brokers import AlpacaBroker
from rapid_portfolio_manager import RapidPortfolioManager


def draw_equity_curve(timestamps, equity, width=60):
    """Draw ASCII equity curve"""
    if not equity or len(equity) < 2:
        print("  No data to display")
        return

    min_equity = min(equity)
    max_equity = max(equity)
    range_equity = max_equity - min_equity

    if range_equity == 0:
        range_equity = max_equity * 0.01  # 1% range for flat line

    # Create chart
    height = 10
    chart = [[' ' for _ in range(width)] for _ in range(height)]

    # Plot points
    for i, eq in enumerate(equity):
        x = int((i / (len(equity) - 1)) * (width - 1))
        y = height - 1 - int(((eq - min_equity) / range_equity) * (height - 1))
        chart[y][x] = '●'

    # Print chart
    print(f"\n  ${max_equity:,.0f} ┤", end='')
    for col in chart[0]:
        print(col, end='')
    print()

    for row in chart[1:-1]:
        print("          │", end='')
        for col in row:
            print(col, end='')
        print()

    print(f"  ${min_equity:,.0f} └", end='')
    print('─' * width)

    # Date labels
    if len(timestamps) >= 2:
        start_date = timestamps[0][-5:]  # MM-DD
        end_date = timestamps[-1][-5:]
        spacing = width - len(start_date) - len(end_date) - 10
        print(f"          {start_date}", end='')
        print(' ' * spacing, end='')
        print(end_date)


def format_sharpe(sharpe):
    """Format Sharpe ratio with rating"""
    if sharpe >= 2:
        return f"{sharpe:.2f} ⭐⭐⭐ (Excellent)"
    elif sharpe >= 1:
        return f"{sharpe:.2f} ⭐⭐ (Good)"
    elif sharpe >= 0:
        return f"{sharpe:.2f} ⭐ (Fair)"
    else:
        return f"{sharpe:.2f} (Poor)"


def main():
    period = sys.argv[1] if len(sys.argv) > 1 else '1M'

    print("=" * 70)
    print("📊 PORTFOLIO PERFORMANCE REPORT")
    print("=" * 70)

    try:
        # Initialize broker
        broker = AlpacaBroker(paper=True)

        # Get portfolio history
        print(f"\n🔄 Fetching portfolio history ({period})...")
        history = broker.get_portfolio_history(period=period, timeframe='1D')

        # Calculate metrics
        metrics = broker.calculate_performance_metrics(history)

        # Convert timestamps
        from datetime import datetime
        timestamps = [
            datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
            for ts in history['timestamp']
        ]

        # Display summary
        print("\n" + "=" * 70)
        print(f"📈 SUMMARY ({period})")
        print("=" * 70)
        print(f"  Start Equity:      ${history['equity'][0]:,.2f}")
        print(f"  Current Equity:    ${history['equity'][-1]:,.2f}")
        print(f"  Total Return:      {metrics['total_return_pct']:+.2f}% (${metrics['total_return_usd']:+,.2f})")
        print(f"  Max Drawdown:      {metrics['max_drawdown_pct']:.2f}% ({metrics['max_drawdown_date']})")
        print(f"  Sharpe Ratio:      {format_sharpe(metrics['sharpe_ratio'])}")
        print(f"  Win Days:          {metrics['win_days']}/{metrics['win_days'] + metrics['loss_days']} ({metrics['win_rate']:.1f}%)")
        print(f"  Avg Daily Return:  {metrics['avg_daily_return']:+.3f}%")
        print(f"  Daily Volatility:  {metrics['volatility']:.3f}%")

        # Draw equity curve
        print("\n" + "=" * 70)
        print("📊 EQUITY CURVE")
        print("=" * 70)
        draw_equity_curve(timestamps, history['equity'])

        # Insights
        print("\n" + "=" * 70)
        print("💡 INSIGHTS")
        print("=" * 70)

        if metrics['sharpe_ratio'] >= 2:
            print("  ✅ Excellent risk-adjusted returns!")
        elif metrics['sharpe_ratio'] >= 1:
            print("  ✅ Good risk-adjusted returns")
        else:
            print("  ⚠️  Low risk-adjusted returns - consider strategy review")

        if abs(metrics['max_drawdown_pct']) < 5:
            print("  ✅ Low drawdown - good risk management")
        elif abs(metrics['max_drawdown_pct']) < 10:
            print("  ⚠️  Moderate drawdown")
        else:
            print(f"  ⚠️  High drawdown ({metrics['max_drawdown_pct']:.1f}%) - review risk settings")

        if metrics['win_rate'] >= 70:
            print(f"  ✅ High win rate ({metrics['win_rate']:.1f}%)")
        elif metrics['win_rate'] >= 50:
            print(f"  ⚠️  Moderate win rate ({metrics['win_rate']:.1f}%)")
        else:
            print(f"  ⚠️  Low win rate ({metrics['win_rate']:.1f}%) - strategy may need adjustment")

        print("\n" + "=" * 70)
        print("✅ Report complete!")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
