#!/usr/bin/env python3
"""
STOCK PERSONALITY ANALYZER - วิเคราะห์ "บุคลิก" ของหุ้น

"เหมือนกับการวิเคราะห์บุคคล - คนสองคนใช้เกณฑ์เดียวกัน
 ก็อาจได้ผลต่างกัน เพราะคนเราไม่เหมือนกัน"

แต่ละหุ้นมีบุคลิกเฉพาะตัว:
- Volatility Personality: สงบ vs ก้าวร้าว
- Trend Personality: ตามเทรนด์ vs สวนเทรนด์
- Volume Personality: active vs quiet
- Reaction Personality: ตอบสนองเร็ว vs ช้า
- Seasonal Personality: ดีเดือนไหน แย่เดือนไหน
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None


@dataclass
class StockPersonality:
    """บุคลิกของหุ้น"""
    symbol: str
    analyzed_at: str

    # Volatility Personality
    volatility_type: str  # CALM, NORMAL, AGGRESSIVE, WILD
    avg_daily_move: float
    max_daily_move: float

    # Trend Personality
    trend_type: str  # TREND_FOLLOWER, MEAN_REVERTER, MIXED
    trend_strength: float  # 0-100

    # Volume Personality
    volume_type: str  # QUIET, NORMAL, ACTIVE, EXPLOSIVE
    avg_volume_ratio: float  # vs 20-day avg

    # Reaction Personality
    earnings_reaction: str  # OVERREACT, NORMAL, UNDERREACT
    news_sensitivity: float  # 0-100

    # Seasonal Personality
    best_months: List[int]
    worst_months: List[int]
    best_day_of_week: int

    # Market Correlation
    spy_correlation: float
    vix_sensitivity: float
    sector_beta: float

    # Trading Characteristics
    avg_win_size: float
    avg_loss_size: float
    win_rate_historical: float
    best_hold_period: int  # days

    # Summary
    trading_style_match: str  # MOMENTUM, SWING, POSITION, AVOID
    confidence_level: int  # 0-100
    summary: str


class StockPersonalityAnalyzer:
    """วิเคราะห์บุคลิกของหุ้น"""

    def __init__(self, data_dir: str = None):
        """Initialize"""
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(__file__), '..', 'data', 'personality'
        )
        os.makedirs(self.data_dir, exist_ok=True)

        self.personalities: Dict[str, StockPersonality] = {}

    def analyze_personality(self, symbol: str) -> Optional[StockPersonality]:
        """วิเคราะห์บุคลิกของหุ้น 1 ตัว"""
        if yf is None:
            return None

        print(f"\nAnalyzing {symbol}...")

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1y')

            if hist.empty or len(hist) < 200:
                print(f"  Insufficient data for {symbol}")
                return None

            closes = hist['Close'].values.flatten()
            volumes = hist['Volume'].values.flatten()
            highs = hist['High'].values.flatten()
            lows = hist['Low'].values.flatten()
            dates = hist.index

            # ===== VOLATILITY PERSONALITY =====
            daily_returns = np.diff(closes) / closes[:-1] * 100
            avg_move = np.mean(np.abs(daily_returns))
            max_move = np.max(np.abs(daily_returns))

            if avg_move < 1.0:
                volatility_type = 'CALM'
            elif avg_move < 2.0:
                volatility_type = 'NORMAL'
            elif avg_move < 3.5:
                volatility_type = 'AGGRESSIVE'
            else:
                volatility_type = 'WILD'

            # ===== TREND PERSONALITY =====
            # Check if stock follows trends or mean-reverts
            ma20 = pd.Series(closes).rolling(20).mean().values
            ma50 = pd.Series(closes).rolling(50).mean().values

            above_ma20 = np.sum(closes[50:] > ma20[50:]) / len(closes[50:])
            above_ma50 = np.sum(closes[50:] > ma50[50:]) / len(closes[50:])

            # Trend strength based on consistency
            if above_ma20 > 0.6 or above_ma20 < 0.4:
                trend_type = 'TREND_FOLLOWER'
                trend_strength = abs(above_ma20 - 0.5) * 200
            else:
                trend_type = 'MEAN_REVERTER'
                trend_strength = 50 - abs(above_ma20 - 0.5) * 100

            # ===== VOLUME PERSONALITY =====
            vol_20d_avg = pd.Series(volumes).rolling(20).mean().values
            vol_ratio = volumes[-20:].mean() / vol_20d_avg[-20:].mean() if vol_20d_avg[-20:].mean() > 0 else 1

            if vol_ratio < 0.7:
                volume_type = 'QUIET'
            elif vol_ratio < 1.3:
                volume_type = 'NORMAL'
            elif vol_ratio < 2.0:
                volume_type = 'ACTIVE'
            else:
                volume_type = 'EXPLOSIVE'

            # ===== SEASONAL PERSONALITY =====
            monthly_returns = {}
            for i in range(len(closes) - 21):
                month = dates[i].month
                ret = (closes[i + 21] / closes[i] - 1) * 100
                if month not in monthly_returns:
                    monthly_returns[month] = []
                monthly_returns[month].append(ret)

            best_months = []
            worst_months = []
            for month, returns in monthly_returns.items():
                avg = np.mean(returns)
                if avg > 2:
                    best_months.append(month)
                elif avg < -2:
                    worst_months.append(month)

            # Day of week analysis
            dow_returns = {i: [] for i in range(5)}
            for i in range(len(daily_returns)):
                dow = dates[i].dayofweek
                if dow < 5:
                    dow_returns[dow].append(daily_returns[i])

            best_dow = max(dow_returns.keys(), key=lambda x: np.mean(dow_returns[x]) if dow_returns[x] else 0)

            # ===== MARKET CORRELATION =====
            spy = yf.download('SPY', period='1y', progress=False)
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)
            spy_returns = np.diff(spy['Close'].values) / spy['Close'].values[:-1]

            min_len = min(len(daily_returns), len(spy_returns))
            spy_corr = np.corrcoef(daily_returns[-min_len:], spy_returns[-min_len:])[0, 1]

            vix = yf.download('^VIX', period='1y', progress=False)
            if isinstance(vix.columns, pd.MultiIndex):
                vix.columns = vix.columns.get_level_values(0)
            vix_values = vix['Close'].values

            # VIX sensitivity
            high_vix_returns = []
            low_vix_returns = []
            for i in range(min(len(daily_returns), len(vix_values) - 1)):
                if vix_values[i] > 20:
                    high_vix_returns.append(daily_returns[i])
                else:
                    low_vix_returns.append(daily_returns[i])

            vix_sens = 50
            if high_vix_returns and low_vix_returns:
                high_avg = np.mean(high_vix_returns)
                low_avg = np.mean(low_vix_returns)
                vix_sens = min(100, max(0, 50 + (low_avg - high_avg) * 20))

            # ===== TRADING CHARACTERISTICS =====
            # Simulate 5-day holds
            wins = []
            losses = []
            for i in range(len(closes) - 5):
                ret = (closes[i + 5] / closes[i] - 1) * 100
                if ret > 0:
                    wins.append(ret)
                else:
                    losses.append(ret)

            avg_win = np.mean(wins) if wins else 0
            avg_loss = np.mean(losses) if losses else 0
            win_rate = len(wins) / (len(wins) + len(losses)) * 100 if (wins or losses) else 50

            # Best hold period
            best_period = 5
            best_return = 0
            for period in [3, 5, 10, 20]:
                if period >= len(closes):
                    continue
                returns = []
                for i in range(len(closes) - period):
                    ret = (closes[i + period] / closes[i] - 1) * 100
                    returns.append(ret)
                avg = np.mean(returns)
                if avg > best_return:
                    best_return = avg
                    best_period = period

            # ===== TRADING STYLE MATCH =====
            if volatility_type in ['CALM', 'NORMAL'] and trend_type == 'TREND_FOLLOWER':
                style = 'MOMENTUM'
            elif volatility_type == 'CALM' and win_rate > 55:
                style = 'POSITION'
            elif volatility_type in ['AGGRESSIVE', 'WILD']:
                style = 'SWING'
            else:
                style = 'SWING'

            # ===== CONFIDENCE LEVEL =====
            confidence = 50
            if win_rate > 55:
                confidence += 15
            if avg_win > abs(avg_loss):
                confidence += 15
            if volatility_type in ['CALM', 'NORMAL']:
                confidence += 10
            if trend_strength > 60:
                confidence += 10

            # ===== SUMMARY =====
            summary = f"{symbol} is a {volatility_type.lower()} stock that tends to {trend_type.lower().replace('_', ' ')}. "
            summary += f"Best traded as {style.lower()} with {best_period}-day holds. "
            if best_months:
                summary += f"Performs well in months: {best_months}. "
            if worst_months:
                summary += f"Avoid months: {worst_months}."

            personality = StockPersonality(
                symbol=symbol,
                analyzed_at=datetime.now().isoformat(),
                volatility_type=volatility_type,
                avg_daily_move=round(avg_move, 2),
                max_daily_move=round(max_move, 2),
                trend_type=trend_type,
                trend_strength=round(trend_strength, 0),
                volume_type=volume_type,
                avg_volume_ratio=round(vol_ratio, 2),
                earnings_reaction='NORMAL',  # Would need earnings data
                news_sensitivity=50,
                best_months=best_months,
                worst_months=worst_months,
                best_day_of_week=best_dow,
                spy_correlation=round(spy_corr, 2),
                vix_sensitivity=round(vix_sens, 0),
                sector_beta=round(spy_corr * 1.2, 2),  # Approximation
                avg_win_size=round(avg_win, 2),
                avg_loss_size=round(avg_loss, 2),
                win_rate_historical=round(win_rate, 1),
                best_hold_period=best_period,
                trading_style_match=style,
                confidence_level=min(100, confidence),
                summary=summary,
            )

            self.personalities[symbol] = personality
            return personality

        except Exception as e:
            print(f"  Error: {e}")
            return None

    def analyze_multiple(self, symbols: List[str]):
        """วิเคราะห์หลายตัว"""
        print("=" * 70)
        print("STOCK PERSONALITY ANALYSIS")
        print("=" * 70)

        for symbol in symbols:
            personality = self.analyze_personality(symbol)
            if personality:
                self._print_personality(personality)

        self._save_all()

    def _print_personality(self, p: StockPersonality):
        """Print personality"""
        print(f"\n{'='*50}")
        print(f"PERSONALITY: {p.symbol}")
        print(f"{'='*50}")

        print(f"""
Volatility: {p.volatility_type} (avg {p.avg_daily_move}%/day)
Trend: {p.trend_type} (strength: {p.trend_strength:.0f})
Volume: {p.volume_type}
SPY Correlation: {p.spy_correlation:.2f}
VIX Sensitivity: {p.vix_sensitivity:.0f}

Historical Performance:
  Win Rate: {p.win_rate_historical:.1f}%
  Avg Win: +{p.avg_win_size:.2f}%
  Avg Loss: {p.avg_loss_size:.2f}%
  Best Hold: {p.best_hold_period} days

Trading Style: {p.trading_style_match}
Confidence: {p.confidence_level}%

Best Months: {p.best_months or 'N/A'}
Worst Months: {p.worst_months or 'N/A'}

Summary: {p.summary}
""")

    def _save_all(self):
        """Save all personalities"""
        # JSON
        json_file = os.path.join(self.data_dir, 'personalities.json')
        with open(json_file, 'w') as f:
            json.dump({s: asdict(p) for s, p in self.personalities.items()}, f, indent=2)

        # Readable
        txt_file = os.path.join(self.data_dir, 'PERSONALITIES.txt')
        with open(txt_file, 'w') as f:
            f.write(f"STOCK PERSONALITIES - {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write("=" * 60 + "\n\n")

            for symbol, p in self.personalities.items():
                f.write(f"{symbol}: {p.volatility_type}, {p.trend_type}\n")
                f.write(f"  Style: {p.trading_style_match}, Confidence: {p.confidence_level}%\n")
                f.write(f"  Win Rate: {p.win_rate_historical}%, Avg Win: +{p.avg_win_size}%\n")
                f.write(f"  {p.summary}\n\n")

        print(f"\nSaved to: {self.data_dir}")


def main():
    """Main"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║              STOCK PERSONALITY ANALYZER                      ║
║   วิเคราะห์ "บุคลิก" ของหุ้น แต่ละตัวไม่เหมือนกัน          ║
╚══════════════════════════════════════════════════════════════╝
""")

    # Analyze top picks from previous analysis
    analyzer = StockPersonalityAnalyzer()
    analyzer.analyze_multiple(['HON', 'RTX', 'CAT', 'HD', 'DIS', 'SCHW', 'MCD', 'LOW'])


if __name__ == '__main__':
    main()
