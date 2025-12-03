"""
Stop Loss Heatmap
แสดงจุดที่มี Stop Loss กองอยู่เยอะ (High Risk Zones for Stop Hunting)

Based on Stop Loss Hunting insights:
- Round numbers (50.00, 100.00) = มี SL เยอะ
- Support/Resistance levels = มี SL เยอะ
- MA levels (50, 200) = มี SL เยอะ
- Fibonacci levels = มี SL เยอะ

จุดเหล่านี้ = เป้าหมายของสถาบันในการล่า SL
"""

from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
from datetime import datetime


class StopLossHeatmap:
    """
    สร้าง Heatmap ของจุดที่มี Stop Loss กองอยู่เยอะ

    ใช้ในการ:
    1. ระบุจุดที่อันตราย (ควรหลีกเลี่ยงวาง SL)
    2. ระบุจุดที่มีโอกาส reversal สูง (หลังถูกล่า SL)
    3. วางแผน entry/exit ให้ดีขึ้น
    """

    def __init__(self, symbol: str):
        self.symbol = symbol

    def generate_heatmap(self,
                        current_price: float,
                        support_resistance: Dict[str, List[float]],
                        ma_levels: Dict[str, float],
                        atr: float,
                        fib_levels: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        สร้าง Stop Loss Heatmap

        Args:
            current_price: ราคาปัจจุบัน
            support_resistance: {'support': [s1, s2, ...], 'resistance': [r1, r2, ...]}
            ma_levels: {'sma_50': value, 'sma_200': value, ...}
            atr: Average True Range
            fib_levels: Optional Fibonacci levels

        Returns:
            Dictionary with heatmap data และ high-risk zones
        """
        clusters = []

        # 1. Round Numbers (เลขกลม)
        round_number_clusters = self._find_round_number_clusters(current_price, atr)
        clusters.extend(round_number_clusters)

        # 2. Support/Resistance Levels
        sr_clusters = self._find_sr_clusters(support_resistance, atr)
        clusters.extend(sr_clusters)

        # 3. MA Levels
        ma_clusters = self._find_ma_clusters(ma_levels, atr)
        clusters.extend(ma_clusters)

        # 4. Fibonacci Levels (if provided)
        if fib_levels:
            fib_clusters = self._find_fib_clusters(fib_levels, atr)
            clusters.extend(fib_clusters)

        # รวม clusters ที่อยู่ใกล้กัน (merge)
        merged_clusters = self._merge_nearby_clusters(clusters, atr)

        # จัดอันดับตามความอันตราย (density)
        ranked_clusters = self._rank_clusters(merged_clusters)

        # หา high-risk zones (clusters ที่มี SL เยอะมาก)
        high_risk_zones = [c for c in ranked_clusters if c['density'] >= 3]

        # หา safe zones (ช่องว่างระหว่าง clusters)
        safe_zones = self._find_safe_zones(ranked_clusters, current_price, atr)

        # คำแนะนำสำหรับ current price
        recommendations = self._generate_recommendations(
            current_price, high_risk_zones, safe_zones, atr
        )

        return {
            'symbol': self.symbol,
            'timestamp': datetime.now().isoformat(),
            'current_price': current_price,
            'all_clusters': ranked_clusters,
            'high_risk_zones': high_risk_zones,
            'safe_zones': safe_zones,
            'recommendations': recommendations,
            'statistics': {
                'total_clusters': len(ranked_clusters),
                'high_risk_count': len(high_risk_zones),
                'safe_zones_count': len(safe_zones),
                'atr': round(atr, 2)
            }
        }

    def _find_round_number_clusters(self, current_price: float, atr: float) -> List[Dict]:
        """หาเลขกลมที่อยู่ใกล้ current price"""
        clusters = []

        # หาช่วงที่จะมองหา (±3 ATR)
        search_range = atr * 3
        min_price = current_price - search_range
        max_price = current_price + search_range

        # หาเลขกลมในช่วงนี้
        # เลขกลม = ลงท้ายด้วย .00 หรือ .50
        start = int(min_price)
        end = int(max_price) + 1

        for price in range(start, end + 1):
            # เลขกลม .00
            if min_price <= price <= max_price:
                clusters.append({
                    'price': float(price),
                    'sources': ['ROUND_NUMBER_00'],
                    'type': 'round_number',
                    'density_score': 2  # เลขกลมมี SL เยอะ
                })

            # เลขกลม .50
            half_price = price + 0.5
            if min_price <= half_price <= max_price:
                clusters.append({
                    'price': half_price,
                    'sources': ['ROUND_NUMBER_50'],
                    'type': 'round_number',
                    'density_score': 1.5  # .50 มี SL น้อยกว่า .00 หน่อย
                })

        return clusters

    def _find_sr_clusters(self, sr_dict: Dict[str, List[float]], atr: float) -> List[Dict]:
        """หา clusters จาก Support/Resistance"""
        clusters = []

        # Support levels
        for support in sr_dict.get('support', []):
            if support and support > 0:
                clusters.append({
                    'price': support,
                    'sources': ['SUPPORT'],
                    'type': 'support_resistance',
                    'density_score': 3  # S/R มี SL เยอะมาก
                })

        # Resistance levels
        for resistance in sr_dict.get('resistance', []):
            if resistance and resistance > 0:
                clusters.append({
                    'price': resistance,
                    'sources': ['RESISTANCE'],
                    'type': 'support_resistance',
                    'density_score': 3
                })

        return clusters

    def _find_ma_clusters(self, ma_levels: Dict[str, float], atr: float) -> List[Dict]:
        """หา clusters จาก MA levels"""
        clusters = []

        critical_mas = ['sma_50', 'sma_200', 'ema_50', 'ema_200']

        for ma_name in critical_mas:
            ma_value = ma_levels.get(ma_name)

            if ma_value and ma_value > 0:
                clusters.append({
                    'price': ma_value,
                    'sources': [ma_name.upper()],
                    'type': 'moving_average',
                    'density_score': 2.5  # MA สำคัญมี SL เยอะ
                })

        return clusters

    def _find_fib_clusters(self, fib_levels: Dict[str, float], atr: float) -> List[Dict]:
        """หา clusters จาก Fibonacci levels"""
        clusters = []

        # Fibonacci levels ที่นิยม
        popular_fibs = ['fib_0.382', 'fib_0.500', 'fib_0.618', 'fib_1.000', 'fib_1.618']

        for fib_name, fib_value in fib_levels.items():
            if fib_name in popular_fibs and fib_value and fib_value > 0:
                clusters.append({
                    'price': fib_value,
                    'sources': [fib_name.upper()],
                    'type': 'fibonacci',
                    'density_score': 2  # Fib levels มี SL พอสมควร
                })

        return clusters

    def _merge_nearby_clusters(self, clusters: List[Dict], atr: float) -> List[Dict]:
        """
        รวม clusters ที่อยู่ใกล้กันมาก (< 0.5 ATR)

        เหตุผล: ถ้ามี support, MA, และ round number อยู่ใกล้กัน
        แสดงว่าจุดนั้นมี SL กองอยู่เยอะมากๆ
        """
        if not clusters:
            return []

        # เรียงตาม price
        sorted_clusters = sorted(clusters, key=lambda x: x['price'])

        merged = []
        current_cluster = sorted_clusters[0].copy()
        current_cluster['sources'] = current_cluster['sources'].copy()

        for i in range(1, len(sorted_clusters)):
            next_cluster = sorted_clusters[i]

            # ถ้าอยู่ใกล้กัน (< 0.5 ATR) ให้รวมกัน
            distance = next_cluster['price'] - current_cluster['price']

            if distance < atr * 0.5:
                # Merge: ใช้ราคาเฉลี่ย และรวม sources
                total_score = current_cluster['density_score'] + next_cluster['density_score']
                current_cluster['price'] = (
                    (current_cluster['price'] * current_cluster['density_score'] +
                     next_cluster['price'] * next_cluster['density_score']) / total_score
                )
                current_cluster['sources'].extend(next_cluster['sources'])
                current_cluster['density_score'] = total_score

                # Update type ถ้ามีหลาย types
                if next_cluster['type'] != current_cluster['type']:
                    current_cluster['type'] = 'multiple'
            else:
                # ไม่ใกล้กัน เก็บ current แล้วเริ่ม cluster ใหม่
                merged.append(current_cluster)
                current_cluster = next_cluster.copy()
                current_cluster['sources'] = current_cluster['sources'].copy()

        # เพิ่ม cluster สุดท้าย
        merged.append(current_cluster)

        return merged

    def _rank_clusters(self, clusters: List[Dict]) -> List[Dict]:
        """จัดอันดับ clusters ตามความหนาแน่นของ SL"""
        for cluster in clusters:
            # คำนวณ density จากจำนวน sources และ density_score
            cluster['density'] = len(cluster['sources'])
            cluster['risk_level'] = self._calculate_risk_level(cluster['density'])

        # เรียงตาม density (สูงสุดก่อน)
        return sorted(clusters, key=lambda x: x['density'], reverse=True)

    def _calculate_risk_level(self, density: int) -> str:
        """คำนวณระดับความเสี่ยงจาก density"""
        if density >= 4:
            return "EXTREME"  # มี SL เยอะมากๆ
        elif density >= 3:
            return "HIGH"
        elif density >= 2:
            return "MEDIUM"
        else:
            return "LOW"

    def _find_safe_zones(self, clusters: List[Dict],
                         current_price: float, atr: float) -> List[Dict]:
        """
        หาช่องว่างระหว่าง clusters (safe zones)
        = จุดที่มี SL น้อย = ปลอดภัยกว่า
        """
        safe_zones = []

        # เรียง clusters ตาม price
        sorted_clusters = sorted(clusters, key=lambda x: x['price'])

        # หาช่องว่างระหว่าง clusters
        for i in range(len(sorted_clusters) - 1):
            lower_cluster = sorted_clusters[i]
            upper_cluster = sorted_clusters[i + 1]

            gap = upper_cluster['price'] - lower_cluster['price']

            # ถ้าช่องว่างกว้างกว่า 1 ATR = safe zone
            if gap > atr * 1.0:
                midpoint = (lower_cluster['price'] + upper_cluster['price']) / 2

                safe_zones.append({
                    'price': round(midpoint, 2),
                    'lower_bound': round(lower_cluster['price'] + atr * 0.3, 2),
                    'upper_bound': round(upper_cluster['price'] - atr * 0.3, 2),
                    'gap_size': round(gap, 2),
                    'quality': 'HIGH' if gap > atr * 2 else 'MEDIUM'
                })

        return safe_zones

    def _generate_recommendations(self, current_price: float,
                                  high_risk_zones: List[Dict],
                                  safe_zones: List[Dict],
                                  atr: float) -> Dict[str, Any]:
        """สร้างคำแนะนำจาก heatmap"""

        recommendations = {
            'current_status': '',
            'warnings': [],
            'safe_sl_suggestions': [],
            'entry_suggestions': []
        }

        # เช็คว่า current price อยู่ใกล้ high-risk zone หรือไม่
        nearby_risks = [
            z for z in high_risk_zones
            if abs(z['price'] - current_price) < atr * 0.5
        ]

        if nearby_risks:
            risk = nearby_risks[0]
            recommendations['current_status'] = f"⚠️ อยู่ใกล้ High-Risk Zone: {risk['price']:.2f}"
            recommendations['warnings'].append(
                f"อย่าวาง SL ใกล้ {risk['price']:.2f} (มี SL กองเยอะ - เสี่ยงโดนล่า)"
            )
        else:
            recommendations['current_status'] = "✅ อยู่ในจุดที่ปลอดภัย"

        # หา safe zones สำหรับวาง SL
        safe_sl_below = [sz for sz in safe_zones if sz['price'] < current_price]
        if safe_sl_below:
            best_safe_zone = safe_sl_below[-1]  # ใกล้ที่สุด
            recommendations['safe_sl_suggestions'].append(
                f"💡 แนะนำวาง SL ที่ {best_safe_zone['price']:.2f} (Safe Zone - มี SL น้อย)"
            )

        # หา high-risk zones ที่อาจมี reversal
        potential_reversals = [
            z for z in high_risk_zones
            if abs(z['price'] - current_price) < atr * 2
        ]

        for zone in potential_reversals[:3]:  # Top 3
            if zone['price'] < current_price:
                recommendations['entry_suggestions'].append(
                    f"🎯 รอ liquidity grab ที่ {zone['price']:.2f} แล้วเข้า Buy"
                )
            else:
                recommendations['entry_suggestions'].append(
                    f"🎯 รอ liquidity grab ที่ {zone['price']:.2f} แล้วเข้า Sell"
                )

        return recommendations


def format_sl_heatmap(result: Dict[str, Any]) -> str:
    """Format Stop Loss Heatmap result"""

    stats = result['statistics']

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗺️ STOP LOSS HEATMAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Current Price: ${result['current_price']:.2f}
ATR: ${stats['atr']:.2f}

{result['recommendations']['current_status']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 HIGH-RISK ZONES ({len(result['high_risk_zones'])}):
(จุดที่มี Stop Loss กองอยู่เยอะ - เสี่ยงโดนล่า!)

"""

    for i, zone in enumerate(result['high_risk_zones'][:5], 1):
        sources_str = ', '.join(zone['sources'])
        output += f"{i}. ${zone['price']:.2f} - Density: {zone['density']} [{zone['risk_level']}]\n"
        output += f"   Sources: {sources_str}\n\n"

    output += f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🟢 SAFE ZONES ({len(result['safe_zones'])}):
(ช่องว่างที่มี Stop Loss น้อย - ปลอดภัยกว่า)

"""

    for i, zone in enumerate(result['safe_zones'][:3], 1):
        output += f"{i}. ${zone['price']:.2f} (Gap: ${zone['gap_size']:.2f}) - {zone['quality']}\n"
        output += f"   Range: ${zone['lower_bound']:.2f} - ${zone['upper_bound']:.2f}\n\n"

    output += f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 RECOMMENDATIONS:

"""

    # Warnings
    if result['recommendations']['warnings']:
        output += "⚠️ Warnings:\n"
        for warning in result['recommendations']['warnings']:
            output += f"   • {warning}\n"
        output += "\n"

    # Safe SL Suggestions
    if result['recommendations']['safe_sl_suggestions']:
        output += "🛡️ Safe Stop Loss:\n"
        for suggestion in result['recommendations']['safe_sl_suggestions']:
            output += f"   • {suggestion}\n"
        output += "\n"

    # Entry Suggestions
    if result['recommendations']['entry_suggestions']:
        output += "🎯 Entry Opportunities:\n"
        for suggestion in result['recommendations']['entry_suggestions'][:3]:
            output += f"   • {suggestion}\n"

    output += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Statistics:
├─ Total Clusters: {stats['total_clusters']}
├─ High-Risk Zones: {stats['high_risk_count']}
└─ Safe Zones: {stats['safe_zones_count']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Insight: หลีกเลี่ยง High-Risk Zones เมื่อวาง Stop Loss!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    return output
