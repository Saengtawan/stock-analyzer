#!/usr/bin/env python3
"""
Comprehensive Test: Hot Sectors - Find all stocks with ≥3 signals
Test across all hot sectors to find hidden opportunities
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from api.data_manager import DataManager
from screeners.growth_catalyst_screener import GrowthCatalystScreener
from sector_rotation import SectorRotationDetector
import logging

logging.basicConfig(level=logging.WARNING)

def main():
    print("\n" + "="*80)
    print("🔍 COMPREHENSIVE HOT SECTOR SCAN")
    print("="*80)

    # Initialize
    print("\nInitializing...")
    data_manager = DataManager()
    screener = GrowthCatalystScreener(data_manager)
    sector_detector = SectorRotationDetector()

    # Get current hot sectors
    print("\n1️⃣ Checking Hot Sectors...")
    sector_momentum = sector_detector.get_sector_momentum()

    print("\n🔥 Current Hot Sectors:")
    for sector in sector_momentum['hot_sectors'][:5]:
        data = sector_momentum['sectors'][sector]
        print(f"   {sector:<30} {data['score']:>+6.1f}%")

    # Test stocks across hot sectors
    test_stocks = {
        # Semiconductors (+7.7%)
        'Semiconductors': ['NVDA', 'AMD', 'AVGO', 'QCOM', 'MRVL', 'LRCX', 'KLAC', 'AMAT', 'MU'],

        # Gold Miners (+16.7%)
        'Gold Miners': ['GDX', 'NEM', 'GOLD', 'AEM', 'FNV'],

        # Financials (+7.6%)
        'Financials': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'SCHW'],

        # Materials (+7.6%)
        'Materials': ['LIN', 'APD', 'ECL', 'FCX', 'NUE'],

        # Technology (neutral +2.7% but has many stocks)
        'Technology': ['MSFT', 'AAPL', 'GOOGL', 'META', 'NFLX', 'TSLA', 'CRM', 'ADBE'],

        # From Backtest (known 3/6 signals)
        'Backtest Winners': ['AVGO', 'RIVN'],
    }

    print("\n2️⃣ Scanning Stocks Across Hot Sectors...")
    print("="*80)

    all_results = []

    for sector_name, symbols in test_stocks.items():
        print(f"\n📊 {sector_name}:")
        print("-" * 60)

        for symbol in symbols:
            try:
                result = screener._analyze_stock_comprehensive(
                    symbol,
                    target_gain_pct=5.0,
                    timeframe_days=30
                )

                if result:
                    signals = result.get('alt_data_signals', 0)
                    score = result.get('composite_score', 0)
                    sector = result.get('sector', 'Unknown')
                    momentum = result.get('sector_momentum', 0)
                    boost = result.get('sector_rotation_boost', 1.0)

                    status = "✅" if signals >= 3 else "⚠️"

                    print(f"  {status} {symbol:<6} {signals}/6 signals | "
                          f"Score: {score:>5.1f} | "
                          f"{sector[:20]:<20} {momentum:>+5.1f}% ({boost:.2f}x)")

                    all_results.append({
                        'symbol': symbol,
                        'sector_group': sector_name,
                        'signals': signals,
                        'score': score,
                        'sector': sector,
                        'momentum': momentum,
                        'boost': boost
                    })
                else:
                    print(f"  ❌ {symbol:<6} Filtered out (< 3 signals or failed criteria)")

            except Exception as e:
                print(f"  ⚠️ {symbol:<6} Error: {str(e)[:50]}")

    # Summary
    print("\n" + "="*80)
    print("📊 COMPREHENSIVE SUMMARY")
    print("="*80)

    # Filter stocks with ≥3 signals
    qualified = [r for r in all_results if r['signals'] >= 3]

    print(f"\nTotal Scanned: {len(all_results)}")
    print(f"Stocks with ≥3 signals: {len(qualified)}")
    print(f"Filtered out: {len(all_results) - len(qualified)}")

    if qualified:
        print("\n" + "="*80)
        print("🎯 QUALIFIED STOCKS (≥3 SIGNALS)")
        print("="*80)

        # Sort by score
        qualified.sort(key=lambda x: x['score'], reverse=True)

        print(f"\n{'Rank':<6} {'Symbol':<8} {'Signals':<10} {'Score':<8} {'Sector':<25} {'Momentum':<12} {'Boost':<8}")
        print("-" * 100)

        for i, stock in enumerate(qualified, 1):
            rank = {1: '🥇', 2: '🥈', 3: '🥉'}.get(i, f'#{i}')
            print(f"{rank:<6} "
                  f"{stock['symbol']:<8} "
                  f"{stock['signals']}/6{'':<6} "
                  f"{stock['score']:>6.1f}  "
                  f"{stock['sector'][:23]:<25} "
                  f"{stock['momentum']:>+6.1f}%{'':<4} "
                  f"{stock['boost']:.2f}x")

        # Group by sector
        print("\n" + "="*80)
        print("📈 BREAKDOWN BY SECTOR")
        print("="*80)

        from collections import defaultdict
        by_sector = defaultdict(list)
        for stock in qualified:
            by_sector[stock['sector']].append(stock)

        for sector, stocks in sorted(by_sector.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"\n{sector} ({len(stocks)} stocks):")
            for s in stocks:
                print(f"  • {s['symbol']:<6} {s['signals']}/6 signals, Score: {s['score']:.1f}")

    else:
        print("\n⚠️ NO STOCKS QUALIFIED")
        print("Possible reasons:")
        print("  - No stocks have ≥3 alternative data signals")
        print("  - All filtered by technical/valuation criteria")
        print("  - API rate limits or data unavailable")

    # Check backtest winners specifically
    print("\n" + "="*80)
    print("🔍 BACKTEST WINNERS CHECK")
    print("="*80)

    backtest_winners = [r for r in all_results if r['symbol'] in ['AVGO', 'RIVN']]

    for winner in backtest_winners:
        print(f"\n{winner['symbol']}:")
        print(f"  Signals: {winner['signals']}/6 (need ≥3)")
        print(f"  Score: {winner['score']:.1f}")
        print(f"  Sector: {winner['sector']} ({winner['momentum']:+.1f}%)")
        print(f"  Status: {'✅ QUALIFIED' if winner['signals'] >= 3 else '❌ BELOW THRESHOLD'}")

    print("\n" + "="*80)
    print("✅ Comprehensive Scan Complete!")
    print("="*80)


if __name__ == "__main__":
    main()
