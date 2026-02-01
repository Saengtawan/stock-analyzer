#!/usr/bin/env python3
"""
MASTER SCREENER - รวมทุก Layer เข้าด้วยกัน

ขั้นตอนการทำงาน:
1. MACRO CHECK → Risk-On/Risk-Off?
2. SECTOR SELECTION → Top 3 sectors
3. CATALYST SCAN → หุ้นที่มีเหตุผลจะขึ้น
4. TECHNICAL FILTER → Entry timing
5. OUTPUT → ซื้อ/ไม่ซื้อ + เหตุผล

เป้าหมาย: หาหุ้นที่มีโอกาสทำกำไร 10-15% ภายใน 2-4 สัปดาห์
"""

import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

# Import our modules
from macro_data_collector import MacroDataCollector
from sector_analyzer import SectorAnalyzer
from catalyst_scanner import CatalystScanner

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'database', 'stocks.db')


class MasterScreener:
    """Master screener that integrates all analysis layers"""

    def __init__(self):
        self.macro_collector = MacroDataCollector()
        self.sector_analyzer = SectorAnalyzer()
        self.catalyst_scanner = CatalystScanner()
        self.db_path = DB_PATH

    def run_full_analysis(self) -> Dict:
        """Run complete analysis pipeline"""
        print("="*70)
        print("🎯 MASTER SCREENER - Full Analysis Pipeline")
        print("="*70)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)

        results = {
            'timestamp': datetime.now().isoformat(),
            'should_buy': False,
            'reason': '',
            'picks': [],
        }

        # ==========================================
        # STEP 1: MACRO CHECK
        # ==========================================
        print("\n" + "="*60)
        print("📊 STEP 1: MACRO CHECK")
        print("="*60)

        macro_summary = self.macro_collector.get_summary()
        regime = macro_summary['regime']

        results['macro'] = {
            'regime': regime['regime'],
            'risk_level': regime['risk_level'],
            'signals': regime['signals'],
        }

        print(f"\n✅ Regime: {regime['regime']}")
        print(f"✅ Risk Level: {regime['risk_level']}")

        # Decision point 1
        if regime['regime'] == 'RISK-OFF' and regime['risk_level'] == 'HIGH':
            results['should_buy'] = False
            results['reason'] = f"❌ MACRO: {regime['regime']} - {regime['risk_level']} risk. Wait for better conditions."
            print(f"\n⚠️ DECISION: {results['reason']}")
            return results

        # ==========================================
        # STEP 2: SECTOR SELECTION
        # ==========================================
        print("\n" + "="*60)
        print("📊 STEP 2: SECTOR SELECTION")
        print("="*60)

        sector_analysis = self.sector_analyzer.analyze(regime['regime'])
        top_sectors = sector_analysis['top_sectors']
        recommendations = sector_analysis['recommendations']

        results['sectors'] = {
            'top_sectors': top_sectors,
            'stock_picks': len(recommendations),
        }

        print(f"\n✅ Top Sectors: {', '.join(top_sectors)}")

        # Decision point 2
        if not recommendations:
            results['should_buy'] = False
            results['reason'] = "❌ SECTOR: No good stocks found in top sectors"
            print(f"\n⚠️ DECISION: {results['reason']}")
            return results

        # ==========================================
        # STEP 3: CATALYST SCAN
        # ==========================================
        print("\n" + "="*60)
        print("📊 STEP 3: CATALYST SCAN")
        print("="*60)

        symbols = [r['symbol'] for r in recommendations]
        catalyst_results = self.catalyst_scanner.scan_symbols(symbols)

        # Merge catalyst info with recommendations
        catalyst_map = {c['symbol']: c for c in catalyst_results}

        for rec in recommendations:
            cat = catalyst_map.get(rec['symbol'], {})
            rec['catalysts'] = cat.get('catalysts', [])
            rec['catalyst_score'] = cat.get('score', 0)

        results['catalysts'] = {
            'stocks_with_catalysts': len([r for r in recommendations if r.get('catalysts')]),
        }

        # ==========================================
        # STEP 4: TECHNICAL FILTER & SCORING
        # ==========================================
        print("\n" + "="*60)
        print("📊 STEP 4: TECHNICAL FILTER & FINAL SCORING")
        print("="*60)

        final_picks = []

        for rec in recommendations:
            # Get detailed technical data
            tech = self._get_technical_data(rec['symbol'])

            if not tech:
                continue

            # FILTERS
            if tech['atr_pct'] > 3:  # Too volatile
                continue
            if tech['rsi'] > 70:  # Overbought
                continue
            if tech['above_ma20'] < 0:  # Below MA20
                continue

            # SCORING
            score = 0

            # Sector score (from sector analysis)
            score += rec.get('sector_score', 0) * 0.3

            # Momentum score
            if 2 < tech['momentum_5d'] < 8:
                score += 20
            elif 0 < tech['momentum_5d'] < 10:
                score += 10

            # Catalyst score
            score += rec.get('catalyst_score', 0) * 0.5

            # Technical score
            if tech['rsi'] < 60:
                score += 10
            if tech['above_ma20'] > 2:
                score += 10
            if tech['volume_ratio'] > 1.2:
                score += 10

            # Risk adjustment
            if regime['risk_level'] == 'HIGH':
                score *= 0.7
            elif regime['risk_level'] == 'LOW':
                score *= 1.2

            rec['final_score'] = score
            rec['technical'] = tech
            rec['entry_price'] = tech['price']
            rec['stop_price'] = tech['price'] * 0.97  # -3%
            rec['target_price'] = tech['price'] * 1.08  # +8% (adjusted up)

            final_picks.append(rec)

        # Sort by final score
        final_picks.sort(key=lambda x: x['final_score'], reverse=True)

        # ==========================================
        # STEP 5: OUTPUT
        # ==========================================
        print("\n" + "="*60)
        print("🎯 STEP 5: FINAL OUTPUT")
        print("="*60)

        if not final_picks:
            results['should_buy'] = False
            results['reason'] = "❌ No stocks passed all filters"
            print(f"\n⚠️ DECISION: {results['reason']}")
            return results

        # Top 5 picks
        top_picks = final_picks[:5]
        results['picks'] = top_picks
        results['should_buy'] = True
        results['reason'] = f"✅ Found {len(top_picks)} high-quality picks"

        # Print final picks
        print(f"\n🎯 TOP {len(top_picks)} PICKS:\n")
        print(f"{'Symbol':<8} {'Sector':<20} {'Score':>6} {'Price':>10} {'Stop':>10} {'Target':>10} {'Catalysts'}")
        print("-"*90)

        for pick in top_picks:
            catalysts = ', '.join(pick.get('catalysts', [])[:2]) or 'Technical'
            print(f"{pick['symbol']:<8} {pick['sector'][:20]:<20} {pick['final_score']:>6.0f} ${pick['entry_price']:>9.2f} ${pick['stop_price']:>9.2f} ${pick['target_price']:>9.2f} {catalysts[:20]}")

        print("-"*90)

        # Summary box
        print("\n" + "="*60)
        print("📋 SUMMARY")
        print("="*60)
        print(f"  Market Regime: {regime['regime']}")
        print(f"  Risk Level: {regime['risk_level']}")
        print(f"  Top Sectors: {', '.join(top_sectors)}")
        print(f"  Stocks Analyzed: {len(recommendations)}")
        print(f"  Final Picks: {len(top_picks)}")
        print(f"  Recommendation: {'BUY' if results['should_buy'] else 'WAIT'}")

        # Save results
        results_path = os.path.join(DATA_DIR, 'predictions', 'master_picks.json')
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n✅ Results saved to: {results_path}")

        return results

    def _get_technical_data(self, symbol: str) -> Optional[Dict]:
        """Get technical data for a symbol"""
        if yf is None:
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='3mo')

            if len(hist) < 60:
                return None

            closes = hist['Close'].values
            highs = hist['High'].values
            lows = hist['Low'].values
            volumes = hist['Volume'].values

            price = closes[-1]

            # Momentum
            mom_5d = (closes[-1] / closes[-5] - 1) * 100 if closes[-5] > 0 else 0
            mom_20d = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 and closes[-20] > 0 else 0

            # MA20
            ma20 = np.mean(closes[-20:])
            above_ma20 = (price / ma20 - 1) * 100

            # RSI
            deltas = np.diff(closes[-15:])
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

            # ATR %
            tr = []
            for i in range(-14, 0):
                tr.append(max(highs[i] - lows[i],
                              abs(highs[i] - closes[i-1]),
                              abs(lows[i] - closes[i-1])))
            atr_pct = (np.mean(tr) / price) * 100 if price > 0 else 0

            # Volume
            vol_avg = np.mean(volumes[-20:-1])
            vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

            return {
                'price': price,
                'momentum_5d': mom_5d,
                'momentum_20d': mom_20d,
                'above_ma20': above_ma20,
                'rsi': rsi,
                'atr_pct': atr_pct,
                'volume_ratio': vol_ratio,
            }

        except Exception as e:
            return None

    def quick_scan(self) -> List[Dict]:
        """Quick scan without full macro analysis"""
        print("="*60)
        print("⚡ QUICK SCAN (Simplified)")
        print("="*60)

        # Get top sector stocks directly
        conn = sqlite3.connect(self.db_path)

        # Focus on proven sectors
        good_sectors = ['Finance_Banks', 'Finance_Insurance', 'Healthcare_Pharma', 'Materials_Chemicals']

        cursor = conn.execute("""
            SELECT DISTINCT symbol, sector FROM stock_prices
            WHERE sector IN (?, ?, ?, ?)
        """, good_sectors)

        symbols = [(row[0], row[1]) for row in cursor.fetchall()]
        conn.close()

        picks = []

        for symbol, sector in symbols[:50]:
            tech = self._get_technical_data(symbol)

            if not tech:
                continue

            # Quick filters
            if tech['atr_pct'] > 2.5:
                continue
            if tech['rsi'] > 65:
                continue
            if tech['momentum_5d'] < 1 or tech['momentum_5d'] > 8:
                continue
            if tech['above_ma20'] < 0:
                continue

            score = tech['momentum_5d'] * 5 + (20 - tech['atr_pct'] * 5) + tech['volume_ratio'] * 5

            picks.append({
                'symbol': symbol,
                'sector': sector,
                'price': tech['price'],
                'score': score,
                'entry': tech['price'],
                'stop': tech['price'] * 0.97,
                'target': tech['price'] * 1.06,
                **tech
            })

        picks.sort(key=lambda x: x['score'], reverse=True)

        # Print results
        print(f"\nFound {len(picks)} quick picks:\n")
        print(f"{'Symbol':<8} {'Sector':<20} {'Price':>10} {'Mom5d':>8} {'RSI':>6} {'ATR%':>6}")
        print("-"*65)

        for pick in picks[:10]:
            print(f"{pick['symbol']:<8} {pick['sector'][:20]:<20} ${pick['price']:>9.2f} {pick['momentum_5d']:>+7.2f}% {pick['rsi']:>5.0f} {pick['atr_pct']:>5.1f}%")

        return picks[:10]


def main():
    """Main entry point"""
    import sys

    screener = MasterScreener()

    if len(sys.argv) > 1 and sys.argv[1] == '--quick':
        picks = screener.quick_scan()
    else:
        results = screener.run_full_analysis()

        print("\n" + "="*70)
        print("🏁 ANALYSIS COMPLETE")
        print("="*70)

        if results['should_buy']:
            print("\n✅ ACTION: Consider buying the top picks")
            print("\nTop Pick Details:")
            for pick in results['picks'][:3]:
                print(f"\n  {pick['symbol']}:")
                print(f"    Entry: ${pick['entry_price']:.2f}")
                print(f"    Stop: ${pick['stop_price']:.2f} (-3%)")
                print(f"    Target: ${pick['target_price']:.2f} (+8%)")
                if pick.get('catalysts'):
                    print(f"    Catalysts: {', '.join(pick['catalysts'])}")
        else:
            print(f"\n⚠️ ACTION: {results['reason']}")


if __name__ == '__main__':
    main()
