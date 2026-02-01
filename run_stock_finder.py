#!/usr/bin/env python3
"""
STOCK FINDER - Run this to find the best stocks automatically

ใช้งานง่าย:
    python run_stock_finder.py              # รันครั้งเดียว
    python run_stock_finder.py --continuous # รันตลอดเวลา
    python run_stock_finder.py --help       # ดูตัวเลือก

ระบบจะ:
1. ตรวจสอบสภาวะตลาด (ขึ้น/ลง/ผันผวน)
2. เลือกกลยุทธ์ที่เหมาะสม
3. วิเคราะห์หุ้นทั้งหมด
4. หาหุ้นที่ดีที่สุดให้คุณ
5. บันทึกผลลัพธ์ไว้ใน data/

คุณแค่มาดูผลลัพธ์!
"""

import os
import sys
import argparse
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description='Stock Finder - Find the best stocks automatically',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_stock_finder.py              # Run once
  python run_stock_finder.py --continuous # Run continuously
  python run_stock_finder.py --mode all   # Find stocks in any market
  python run_stock_finder.py --mode momentum # Find momentum stocks only
        """
    )

    parser.add_argument(
        '--mode', '-m',
        choices=['all', 'momentum', 'master'],
        default='all',
        help='Analysis mode: all (works in any market), momentum (bull market), master (comprehensive)'
    )

    parser.add_argument(
        '--continuous', '-c',
        action='store_true',
        help='Run continuously (every 10 minutes)'
    )

    parser.add_argument(
        '--cycles', '-n',
        type=int,
        default=1,
        help='Number of cycles to run (default: 1)'
    )

    parser.add_argument(
        '--output', '-o',
        help='Output directory (default: data/)'
    )

    args = parser.parse_args()

    print("""
╔══════════════════════════════════════════════════════════════╗
║                     STOCK FINDER                             ║
║   "แม้วันที่แย่ที่สุด มันต้องมีหุ้นที่ราคาขึ้นบ้าง"        ║
╚══════════════════════════════════════════════════════════════╝
    """)

    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {args.mode}")
    print(f"Continuous: {args.continuous}")
    print()

    try:
        if args.mode == 'all':
            from src.data_sources.all_market_finder import AllMarketFinder
            finder = AllMarketFinder()
            if args.continuous:
                finder.run()
            else:
                finder.run(max_cycles=args.cycles)

        elif args.mode == 'momentum':
            from src.data_sources.continuous_analyzer import ContinuousAnalyzer
            analyzer = ContinuousAnalyzer()
            if args.continuous:
                analyzer.run()
            else:
                analyzer.run(max_cycles=args.cycles)

        elif args.mode == 'master':
            from src.data_sources.master_stock_finder import MasterStockFinder
            finder = MasterStockFinder()
            if args.continuous:
                finder.run()
            else:
                finder.run_once()

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except ImportError as e:
        print(f"Error importing module: {e}")
        print("Make sure all dependencies are installed:")
        print("  pip install yfinance pandas numpy")
    except Exception as e:
        print(f"Error: {e}")
        raise

    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nResults saved to: data/")
    print("  - PICKS.txt (easy to read)")
    print("  - LATEST_PICKS.json (full details)")


if __name__ == '__main__':
    main()
