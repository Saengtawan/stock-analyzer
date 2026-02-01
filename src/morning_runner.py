#!/usr/bin/env python3
"""
MORNING RUNNER - รันอัตโนมัติทุกเช้า

Features:
1. อัพเดตราคาหุ้น
2. ดึงข่าว
3. วิเคราะห์ Macro/Sentiment
4. วิเคราะห์ Sector
5. สแกนหาโอกาส
6. ส่ง Report

Usage:
    # Run once
    python src/morning_runner.py

    # Run with schedule (every day at 6:30 AM)
    python src/morning_runner.py --schedule

    # Run as cron job (add to crontab -e)
    30 6 * * 1-5 cd /path/to/stock-analyzer && python src/morning_runner.py >> logs/morning.log 2>&1
"""

import os
import sys
import json
import time
import schedule
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    import yfinance as yf
except ImportError:
    yf = None

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
LOG_DIR = os.path.join(DATA_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


class MorningRunner:
    """Morning automation runner"""

    def __init__(self):
        self.log_file = os.path.join(LOG_DIR, f"morning_{datetime.now().strftime('%Y%m%d')}.log")
        self.report = {
            'timestamp': datetime.now().isoformat(),
            'status': 'running',
            'steps': {},
        }

    def log(self, message: str, level: str = 'INFO'):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] [{level}] {message}"
        print(log_msg)
        with open(self.log_file, 'a') as f:
            f.write(log_msg + '\n')

    def run_morning_routine(self):
        """Run complete morning routine"""
        self.log("="*60)
        self.log("🌅 MORNING ROUTINE STARTED")
        self.log("="*60)

        start_time = time.time()
        success = True

        # Step 1: Update prices
        self.log("\n📈 Step 1: Updating stock prices...")
        try:
            from data_collector import update_prices
            update_prices()
            self.report['steps']['update_prices'] = 'success'
            self.log("✅ Prices updated")
        except Exception as e:
            self.log(f"❌ Error updating prices: {e}", 'ERROR')
            self.report['steps']['update_prices'] = f'error: {e}'
            # Continue anyway

        # Step 2: Collect news
        self.log("\n📰 Step 2: Collecting news...")
        try:
            from news_collector import NewsCollector
            collector = NewsCollector()
            news_report = collector.generate_news_report()
            self.report['steps']['news'] = 'success'
            self.report['news_summary'] = {
                'articles': news_report.get('articles_count', 0),
            }
            self.log("✅ News collected")
        except Exception as e:
            self.log(f"⚠️ News collection skipped: {e}", 'WARNING')
            self.report['steps']['news'] = f'skipped: {e}'

        # Step 3: Macro analysis
        self.log("\n📊 Step 3: Macro analysis...")
        try:
            from macro_data_collector import MacroDataCollector
            macro = MacroDataCollector()
            macro_summary = macro.get_summary()
            self.report['steps']['macro'] = 'success'
            self.report['macro'] = {
                'regime': macro_summary.get('regime', {}).get('regime', 'UNKNOWN'),
                'risk_level': macro_summary.get('regime', {}).get('risk_level', 'UNKNOWN'),
            }
            self.log(f"✅ Macro: {self.report['macro']['regime']}, Risk: {self.report['macro']['risk_level']}")
        except Exception as e:
            self.log(f"❌ Error in macro analysis: {e}", 'ERROR')
            self.report['steps']['macro'] = f'error: {e}'

        # Step 4: Sector analysis
        self.log("\n📊 Step 4: Sector analysis...")
        try:
            from sector_analyzer import SectorAnalyzer
            sector = SectorAnalyzer()
            sector_analysis = sector.analyze()
            self.report['steps']['sector'] = 'success'
            self.report['sectors'] = {
                'top_sectors': sector_analysis.get('top_sectors', []),
            }
            self.log(f"✅ Top Sectors: {', '.join(self.report['sectors']['top_sectors'][:3])}")
        except Exception as e:
            self.log(f"❌ Error in sector analysis: {e}", 'ERROR')
            self.report['steps']['sector'] = f'error: {e}'

        # Step 5: Complete analysis
        self.log("\n🎯 Step 5: Complete analysis...")
        try:
            from complete_analyzer import CompleteAnalyzer
            analyzer = CompleteAnalyzer()
            analysis = analyzer.run_all_steps()
            self.report['steps']['analysis'] = 'success'
            self.report['picks'] = analysis.get('picks', [])
            self.log(f"✅ Found {len(self.report['picks'])} picks")
        except Exception as e:
            self.log(f"❌ Error in complete analysis: {e}", 'ERROR')
            self.report['steps']['analysis'] = f'error: {e}'
            success = False

        # Step 6: Portfolio update
        self.log("\n💼 Step 6: Portfolio update...")
        try:
            from portfolio_system import PortfolioManager
            pm = PortfolioManager()
            alerts = pm.update_prices()
            self.report['steps']['portfolio'] = 'success'
            self.report['portfolio_alerts'] = len(alerts) if alerts else 0
            self.log(f"✅ Portfolio updated, {self.report['portfolio_alerts']} alerts")
        except Exception as e:
            self.log(f"⚠️ Portfolio update skipped: {e}", 'WARNING')
            self.report['steps']['portfolio'] = f'skipped: {e}'

        # Generate final report
        elapsed = time.time() - start_time
        self.report['status'] = 'completed' if success else 'completed_with_errors'
        self.report['elapsed_seconds'] = elapsed

        # Save report
        report_path = os.path.join(LOG_DIR, f"morning_report_{datetime.now().strftime('%Y%m%d')}.json")
        with open(report_path, 'w') as f:
            json.dump(self.report, f, indent=2, default=str)

        # Print summary
        self.log("\n" + "="*60)
        self.log("📋 MORNING ROUTINE SUMMARY")
        self.log("="*60)
        self.log(f"Status: {self.report['status']}")
        self.log(f"Duration: {elapsed:.1f} seconds")

        if self.report.get('macro'):
            self.log(f"Market: {self.report['macro']['regime']} (Risk: {self.report['macro']['risk_level']})")

        if self.report.get('sectors'):
            self.log(f"Top Sectors: {', '.join(self.report['sectors']['top_sectors'][:3])}")

        if self.report.get('picks'):
            self.log(f"\n🎯 TODAY'S PICKS:")
            for pick in self.report['picks'][:5]:
                self.log(f"  • {pick['symbol']}: Entry ${pick['entry_price']:.2f}, Stop ${pick['stop_price']:.2f}, Target ${pick['target_price']:.2f}")

        self.log(f"\n✅ Report saved to: {report_path}")

        return self.report

    def run_scheduled(self, run_time: str = "06:30"):
        """Run scheduled (every trading day)"""
        self.log(f"⏰ Scheduler started. Running every weekday at {run_time}")

        # Schedule for weekdays only
        schedule.every().monday.at(run_time).do(self.run_morning_routine)
        schedule.every().tuesday.at(run_time).do(self.run_morning_routine)
        schedule.every().wednesday.at(run_time).do(self.run_morning_routine)
        schedule.every().thursday.at(run_time).do(self.run_morning_routine)
        schedule.every().friday.at(run_time).do(self.run_morning_routine)

        self.log("Waiting for next scheduled run...")

        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute


def create_cron_script():
    """Create a script for cron job"""
    script_content = f'''#!/bin/bash
# Morning Runner Cron Script
# Add to crontab: crontab -e
# 30 6 * * 1-5 {os.path.dirname(os.path.abspath(__file__))}/../run_morning.sh

cd "{os.path.dirname(os.path.abspath(__file__))}/.."
source venv/bin/activate 2>/dev/null || true

python src/morning_runner.py >> data/logs/morning.log 2>&1

echo "Morning routine completed at $(date)"
'''

    script_path = os.path.join(os.path.dirname(__file__), '..', 'run_morning.sh')
    with open(script_path, 'w') as f:
        f.write(script_content)

    os.chmod(script_path, 0o755)
    print(f"Created: {script_path}")
    print("\nTo set up automatic daily runs:")
    print("1. Edit crontab: crontab -e")
    print(f"2. Add line: 30 6 * * 1-5 {os.path.abspath(script_path)}")
    print("   (This runs at 6:30 AM, Monday-Friday)")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Morning Runner')
    parser.add_argument('--schedule', action='store_true', help='Run in scheduled mode')
    parser.add_argument('--time', default='06:30', help='Daily run time (default: 06:30)')
    parser.add_argument('--create-cron', action='store_true', help='Create cron script')
    args = parser.parse_args()

    if args.create_cron:
        create_cron_script()
    elif args.schedule:
        runner = MorningRunner()
        runner.run_scheduled(run_time=args.time)
    else:
        runner = MorningRunner()
        runner.run_morning_routine()


if __name__ == '__main__':
    main()
