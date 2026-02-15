#!/usr/bin/env python3
"""
Run All Backtests (v6.26)

Execute both backtest scripts and generate summary report
"""

import subprocess
import json
import os
from datetime import datetime

def run_backtest(script_name: str) -> dict:
    """Run a backtest script and return metrics"""
    print(f"\n{'='*80}")
    print(f"Running: {script_name}")
    print(f"{'='*80}\n")

    try:
        result = subprocess.run(
            ['python', script_name],
            cwd='/home/saengtawan/work/project/cc/stock-analyzer',
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        print(result.stdout)

        if result.returncode != 0:
            print(f"❌ Error running {script_name}:")
            print(result.stderr)
            return {'error': result.stderr}

        # Load metrics
        metrics_file = script_name.replace('.py', '_metrics.json')
        if os.path.exists(metrics_file):
            with open(metrics_file, 'r') as f:
                return json.load(f)
        else:
            return {'error': 'Metrics file not found'}

    except subprocess.TimeoutExpired:
        print(f"❌ Timeout running {script_name}")
        return {'error': 'Timeout'}
    except Exception as e:
        print(f"❌ Exception running {script_name}: {e}")
        return {'error': str(e)}


def generate_summary_report(evening_risk_metrics: dict, weekend_review_metrics: dict):
    """Generate summary report comparing both features"""

    report = []
    report.append("\n" + "="*80)
    report.append("BACKTEST SUMMARY REPORT")
    report.append("="*80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("="*80)

    # Evening Risk Analysis
    report.append("\n📊 Feature 1: Evening Risk Analysis (Pre-SL Exit)")
    report.append("-" * 80)

    if 'error' not in evening_risk_metrics:
        report.append(f"  Total instances analyzed: {evening_risk_metrics.get('total_instances', 0)}")
        report.append(f"  Actions taken: {evening_risk_metrics.get('actions_taken', 0)}")
        report.append(f"  Avg improvement: {evening_risk_metrics.get('avg_improvement', 0):+.2f}%")
        report.append(f"  False exit rate: {evening_risk_metrics.get('false_exit_rate', 0):.1f}%")
        report.append(f"  Max loss reduction: {evening_risk_metrics.get('max_loss_reduction', 0):+.2f}%")
        report.append(f"  Dollar impact: ${evening_risk_metrics.get('total_dollar_impact', 0):+,.2f}")
        report.append(f"  Criteria met: {evening_risk_metrics.get('criteria_met', 0)}/3")
        report.append(f"  Recommendation: {evening_risk_metrics.get('recommendation', 'UNKNOWN')}")
    else:
        report.append(f"  ❌ Error: {evening_risk_metrics.get('error')}")

    # Weekend Position Review
    report.append("\n📊 Feature 2: Weekend Position Review")
    report.append("-" * 80)

    if 'error' not in weekend_review_metrics:
        report.append(f"  Total reviews analyzed: {weekend_review_metrics.get('total_reviews', 0)}")
        report.append(f"  Actions taken: {weekend_review_metrics.get('actions_taken', 0)}")
        report.append(f"  Avg improvement: {weekend_review_metrics.get('avg_improvement', 0):+.2f}%")
        report.append(f"  False rotation rate: {weekend_review_metrics.get('false_rotation_rate', 0):.1f}%")
        report.append(f"  Early exit benefit: {weekend_review_metrics.get('early_exit_benefit', 0):+.2f}%")
        report.append(f"  Avg days saved: {weekend_review_metrics.get('avg_days_saved', 0):.1f}")
        report.append(f"  Dollar impact: ${weekend_review_metrics.get('total_dollar_impact', 0):+,.2f}")
        report.append(f"  Criteria met: {weekend_review_metrics.get('criteria_met', 0)}/3")
        report.append(f"  Recommendation: {weekend_review_metrics.get('recommendation', 'UNKNOWN')}")
    else:
        report.append(f"  ❌ Error: {weekend_review_metrics.get('error')}")

    # Final recommendation
    report.append("\n" + "="*80)
    report.append("FINAL RECOMMENDATIONS")
    report.append("="*80)

    evening_rec = evening_risk_metrics.get('recommendation', 'SKIP')
    weekend_rec = weekend_review_metrics.get('recommendation', 'SKIP')

    if evening_rec == 'IMPLEMENT' and weekend_rec == 'IMPLEMENT':
        report.append("🎯 IMPLEMENT BOTH FEATURES")
        report.append("   Both features showed significant improvement")
        report.append("")
        report.append("   Next Steps:")
        report.append("   1. Implement Evening Risk Analysis cron (6 PM daily)")
        report.append("   2. Implement Weekend Review cron (Sunday 8 PM)")
        report.append("   3. Integrate with Auto Trading Engine")
        report.append("   4. Paper trade for 2 weeks")
        report.append("   5. Go live with 50% capital")

    elif evening_rec == 'IMPLEMENT':
        report.append("🎯 IMPLEMENT Evening Risk Analysis ONLY")
        report.append("   Evening Risk showed improvement, Weekend Review did not meet criteria")
        report.append("")
        report.append("   Next Steps:")
        report.append("   1. Implement Evening Risk Analysis cron (6 PM daily)")
        report.append("   2. Paper trade for 2 weeks")
        report.append("   3. Re-evaluate Weekend Review with more data")

    elif weekend_rec == 'IMPLEMENT':
        report.append("🎯 IMPLEMENT Weekend Position Review ONLY")
        report.append("   Weekend Review showed improvement, Evening Risk did not meet criteria")
        report.append("")
        report.append("   Next Steps:")
        report.append("   1. Implement Weekend Review cron (Sunday 8 PM)")
        report.append("   2. Paper trade for 2 weeks")
        report.append("   3. Re-evaluate Evening Risk with more data")

    else:
        report.append("❌ SKIP BOTH FEATURES")
        report.append("   Neither feature met minimum criteria for implementation")
        report.append("")
        report.append("   Reasons:")
        if 'error' not in evening_risk_metrics:
            report.append(f"   - Evening Risk: {evening_risk_metrics.get('criteria_met', 0)}/3 criteria met")
        if 'error' not in weekend_review_metrics:
            report.append(f"   - Weekend Review: {weekend_review_metrics.get('criteria_met', 0)}/3 criteria met")
        report.append("")
        report.append("   Next Steps:")
        report.append("   1. Analyze why features underperformed")
        report.append("   2. Adjust parameters and re-test")
        report.append("   3. Consider alternative approaches")

    report.append("="*80 + "\n")

    # Print and save report
    report_text = '\n'.join(report)
    print(report_text)

    with open('backtests/summary_report.txt', 'w') as f:
        f.write(report_text)

    print("✅ Summary report saved to: backtests/summary_report.txt\n")


def main():
    """Run all backtests and generate summary"""

    print("\n" + "="*80)
    print("BACKTEST RUNNER - v6.26")
    print("="*80)
    print("Running both backtest scripts...")
    print("This may take 5-10 minutes depending on data size")
    print("="*80 + "\n")

    # Run Evening Risk Analysis
    evening_metrics = run_backtest('backtests/backtest_evening_risk_analysis.py')

    # Run Weekend Position Review
    weekend_metrics = run_backtest('backtests/backtest_weekend_review.py')

    # Generate summary report
    generate_summary_report(evening_metrics, weekend_metrics)

    # Save combined metrics
    combined = {
        'evening_risk_analysis': evening_metrics,
        'weekend_position_review': weekend_metrics,
        'timestamp': datetime.now().isoformat()
    }

    with open('backtests/combined_metrics.json', 'w') as f:
        json.dump(combined, f, indent=2)

    print("✅ Combined metrics saved to: backtests/combined_metrics.json")
    print("\n🎯 All backtests complete!")


if __name__ == '__main__':
    main()
