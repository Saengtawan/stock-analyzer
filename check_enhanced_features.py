#!/usr/bin/env python3
"""
ตรวจสอบข้อมูล Enhanced Features
"""
import requests
import json

def check_enhanced_features(symbol="AFRM"):
    print(f"\n{'='*70}")
    print(f"🔍 ตรวจสอบ Enhanced Features สำหรับ {symbol}")
    print(f"{'='*70}\n")

    url = "http://127.0.0.1:5002/api/analyze"
    data = {
        "symbol": symbol,
        "time_horizon": "short",
        "account_value": 100000
    }

    try:
        response = requests.post(url, json=data, timeout=120)
        result = response.json()

        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            return

        # Check enhanced_features
        if 'enhanced_features' not in result:
            print("❌ ไม่พบ enhanced_features ใน response")
            print(f"Keys available: {list(result.keys())[:10]}")
            return

        ef = result['enhanced_features']
        print("✅ พบ enhanced_features!\n")

        if 'features' not in ef:
            print("❌ ไม่พบ 'features' ใน enhanced_features")
            return

        features = ef['features']

        # === 1. Position Tracker (P&L) ===
        print("="*70)
        print("💰 1. POSITION TRACKER (P&L)")
        print("="*70)
        if 'pnl_tracker' in features:
            pnl = features['pnl_tracker']
            entry = pnl.get('entry', {})
            current = pnl.get('current', {})
            targets = pnl.get('targets', {})

            print(f"📍 จุดเข้า (Entry):")
            print(f"   • ราคา: ${entry.get('price', 0):.2f}")
            print(f"   • วิธี: {entry.get('method', 'N/A')}")

            profit_pct = current.get('profit_pct', 0)
            profit_dollars = current.get('profit_dollars', 0)
            print(f"\n💵 กำไร/ขาดทุนปัจจุบัน:")
            print(f"   • {profit_pct:+.2f}% (${profit_dollars:+.2f})")

            tp1_progress = current.get('tp1_progress_pct', 0)
            print(f"\n🎯 ความคืบหน้าไป TP1:")
            print(f"   • {tp1_progress:.1f}% ของทางที่จะถึง TP1")

            print(f"\n🎯 เป้าหมาย:")
            tp1 = targets.get('tp1', 0) if isinstance(targets.get('tp1'), (int, float)) else 0
            tp2 = targets.get('tp2', 0) if isinstance(targets.get('tp2'), (int, float)) else 0
            print(f"   • TP1: ${tp1:.2f}")
            print(f"   • TP2: ${tp2:.2f}")

            print(f"\n✅ ข้อมูล P&L Tracker ถูกต้อง")
        else:
            print("❌ ไม่พบ pnl_tracker")

        # === 2. Trailing Stop Manager ===
        print(f"\n{'='*70}")
        print("🛡️ 2. TRAILING STOP MANAGER")
        print("="*70)
        if 'trailing_stop' in features:
            ts = features['trailing_stop']

            should_move = ts.get('should_move', False)
            original_sl = ts.get('original_sl', 0)
            new_sl = ts.get('new_sl', 0)
            locked_profit = ts.get('locked_profit_pct', 0)
            reason = ts.get('reason', 'N/A')

            print(f"📊 คำแนะนำ: {'✅ ควรขยับ Stop Loss' if should_move else '⏸️ รักษา SL เดิม'}")
            print(f"\n💰 Stop Loss:")
            print(f"   • SL เดิม: ${original_sl:.2f}")
            print(f"   • SL แนะนำ: ${new_sl:.2f}")

            print(f"\n🔒 กำไรที่ล็อคได้:")
            print(f"   • {locked_profit:+.1f}%")

            print(f"\n💡 เหตุผล:")
            print(f"   {reason}")

            print(f"\n✅ ข้อมูล Trailing Stop ถูกต้อง")
        else:
            print("❌ ไม่พบ trailing_stop")

        # === 3. Short Interest ===
        print(f"\n{'='*70}")
        print("🎯 3. SHORT INTEREST ANALYSIS")
        print("="*70)
        if 'short_interest' in features:
            si = features['short_interest']
            si_data = si.get('short_interest', {})

            short_pct = si_data.get('short_pct_float', 0)
            days_to_cover = si_data.get('days_to_cover', 0)
            squeeze = si.get('squeeze_potential', 'N/A')

            print(f"📊 Short Interest:")
            print(f"   • Short %: {short_pct:.1f}%")
            print(f"   • Days to Cover: {days_to_cover:.1f} วัน")
            print(f"   • Squeeze Potential: {squeeze}")

            interp = si.get('interpretation', 'N/A')
            print(f"\n💡 ความหมาย:")
            print(f"   {interp}")

            print(f"\n✅ ข้อมูล Short Interest ถูกต้อง")
        else:
            print("❌ ไม่พบ short_interest")

        # === 4. Risk Alerts ===
        print(f"\n{'='*70}")
        print("⚠️ 4. RISK ALERTS")
        print("="*70)
        if 'risk_alerts' in features:
            ra = features['risk_alerts']

            risk_score = ra.get('risk_score', 0)
            status = ra.get('status', 'N/A')
            alerts = ra.get('alerts', [])
            actions = ra.get('recommended_actions', [])

            print(f"📊 Risk Score: {risk_score}/10")
            print(f"🚦 สถานะ: {status}")

            print(f"\n⚠️ การแจ้งเตือน ({len(alerts)} รายการ):")
            if alerts:
                for i, alert in enumerate(alerts, 1):
                    severity = alert.get('severity', 'N/A')
                    title = alert.get('title', 'N/A')
                    message = alert.get('message', 'N/A')
                    print(f"   {i}. [{severity.upper()}] {title}")
                    print(f"      → {message}")
            else:
                print("   ✅ ไม่มีการแจ้งเตือน")

            print(f"\n💡 คำแนะนำ ({len(actions)} รายการ):")
            for i, action in enumerate(actions, 1):
                print(f"   {i}. {action}")

            print(f"\n✅ ข้อมูล Risk Alerts ถูกต้อง")
        else:
            print("❌ ไม่พบ risk_alerts")

        print(f"\n{'='*70}")
        print("✅ ตรวจสอบข้อมูลทั้งหมดเสร็จสิ้น")
        print(f"{'='*70}\n")

    except requests.exceptions.Timeout:
        print("❌ Timeout - API ใช้เวลานานเกินไป")
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error - ไม่สามารถเชื่อมต่อ server")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AFRM"
    check_enhanced_features(symbol)
