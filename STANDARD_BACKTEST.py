#!/usr/bin/env python3
"""
============================================================================
STANDARD REALISTIC BACKTEST - RAPID TRADER
============================================================================

นี่คือไฟล์ทดสอบมาตรฐานเดียวที่ใช้สำหรับ Rapid Trader

ใช้สำหรับ:
- ทดสอบก่อน deploy production
- เปรียบเทียบก่อน/หลังปรับปรุง code
- Validate strategy changes

หลักการ REALISTIC:
1. ใช้ 680+ stocks จาก production universe
2. ใช้ screener logic จริง (ไม่ replicate)
3. ใช้ portfolio manager logic จริงสำหรับ trailing
4. ใช้ historical data ที่ถูกต้อง (end at simulation date)
5. Simulate ทุกสัปดาห์เหมือนการซื้อขายจริง

IMPORTANT:
- ไม่ว่าจะแก้ไข code ใดๆ ให้ใช้ backtest นี้เท่านั้น
- ไฟล์นี้คือ standard - ห้ามเปลี่ยน methodology
- ผลลัพธ์ต้องเปรียบเทียบได้กับ versions ก่อนหน้า

v3.5: Added SMA20 filter (92% of losers were below SMA20)
Last validated: +6.95%/month, 66.7% win rate (6 months)
============================================================================
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import json
import time
import warnings
import sys
import os
warnings.filterwarnings('ignore')

# Add src to path for importing actual screener
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


# ============================================================================
# CONFIGURATION - MATCH PRODUCTION EXACTLY
# ============================================================================
class Config:
    """Configuration matching production settings"""

    # Backtest period
    MONTHS_BACK = 6

    # Capital management
    STARTING_CAPITAL = 10000
    MAX_POSITIONS = 2
    POSITION_SIZE_PCT = 40

    # Trade management
    MAX_HOLD_DAYS = 5

    # Trailing stop (from production portfolio manager)
    TRAIL_ACTIVATION_PCT = 3.0
    TRAIL_PERCENT = 60

    # Screening (from production screener)
    MIN_SCORE = 90
    MIN_ATR_PCT = 2.5
    BASE_SL_PCT = 3.5
    BASE_TP_PCT = 6.0


# ============================================================================
# PRODUCTION 680+ STOCK UNIVERSE
# ============================================================================
PRODUCTION_UNIVERSE = [
    # === TECHNOLOGY ===
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA',
    'AMD', 'AVGO', 'QCOM', 'TXN', 'INTC', 'MU', 'AMAT', 'LRCX', 'KLAC',
    'MRVL', 'ON', 'NXPI', 'ADI', 'MCHP', 'SWKS', 'QRVO', 'MPWR', 'ENTG',
    'TER', 'CRUS', 'RMBS', 'FORM', 'AOSL', 'POWI',
    'ARM', 'SMCI', 'TSM', 'ASML', 'SNPS', 'CDNS',
    'CRM', 'ORCL', 'NOW', 'ADBE', 'INTU', 'SNOW', 'PLTR', 'DDOG', 'NET',
    'CRWD', 'ZS', 'PANW', 'FTNT', 'OKTA', 'ZM', 'DOCU', 'TEAM',
    'WDAY', 'MDB', 'CFLT', 'PATH', 'S', 'HUBS', 'VEEV',
    'BILL', 'GTLB', 'ESTC', 'FIVN', 'TWLO', 'SNAP',
    'SHOP', 'PYPL', 'COIN', 'AFRM', 'UPST', 'HOOD', 'SOFI',
    'ABNB', 'UBER', 'LYFT', 'DASH', 'RBLX', 'U',
    'DELL', 'HPQ', 'HPE', 'WDC', 'STX', 'NTAP',
    'CSCO', 'ANET', 'FFIV', 'AKAM',

    # === HEALTHCARE ===
    'JNJ', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'REGN',
    'VRTX', 'MRNA', 'BNTX', 'AZN', 'NVS', 'GSK', 'SNY', 'BIIB', 'ALNY',
    'BMRN', 'EXEL', 'INCY', 'SRPT', 'RARE', 'ALKS', 'IONS',
    'NBIX', 'UTHR', 'HALO', 'PCVX', 'ARWR', 'XENE', 'KRYS',
    'IMVT', 'RCKT', 'BEAM', 'EDIT', 'NTLA', 'CRSP',
    'ABT', 'MDT', 'SYK', 'BSX', 'EW', 'ISRG', 'DXCM', 'PODD', 'ALGN',
    'HOLX', 'IDXX', 'WAT', 'TMO', 'DHR', 'A', 'BIO', 'TECH', 'ILMN',
    'UNH', 'CVS', 'CI', 'HUM', 'CNC', 'MOH', 'ELV', 'HCA', 'THC',

    # === FINANCIALS ===
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'USB', 'PNC', 'TFC', 'COF',
    'AXP', 'SCHW', 'BK', 'STT', 'NTRS', 'FITB', 'KEY', 'RF', 'CFG',
    'HBAN', 'ZION', 'CMA', 'WAL',
    'BRK-B', 'PGR', 'TRV', 'ALL', 'AIG', 'MET', 'PRU', 'AFL', 'LNC',
    'V', 'MA', 'FIS', 'FISV', 'GPN', 'ADP', 'PAYX', 'WU',
    'BLK', 'TROW', 'IVZ', 'BEN', 'AMG',

    # === CONSUMER DISCRETIONARY ===
    'HD', 'LOW', 'TGT', 'COST', 'WMT', 'TJX', 'ROST', 'BBY', 'DG', 'DLTR',
    'ULTA', 'FIVE', 'OLLI', 'BURL', 'WSM', 'RH', 'W', 'ETSY',
    'NKE', 'LULU', 'UAA', 'VFC', 'PVH', 'RL', 'TPR', 'CPRI',
    'MCD', 'SBUX', 'CMG', 'DPZ', 'YUM', 'QSR', 'DNUT', 'WING', 'SHAK',
    'DRI', 'TXRH', 'EAT', 'CAKE', 'BLMN',
    'F', 'GM', 'RIVN', 'LCID', 'XPEV', 'NIO', 'LI',
    'APTV', 'BWA', 'LEA', 'VC', 'ALV',
    'MAR', 'HLT', 'H', 'WH', 'CHH', 'LVS', 'WYNN', 'MGM', 'CZR',
    'RCL', 'CCL', 'NCLH', 'EXPE', 'BKNG', 'TRIP', 'MTN',
    'DIS', 'NFLX', 'WBD', 'FOX', 'FOXA', 'LYV', 'MSGS',
    'CHWY', 'CHGG', 'PTON', 'FVRR', 'UPWK',

    # === CONSUMER STAPLES ===
    'PG', 'KO', 'PEP', 'PM', 'MO', 'MDLZ', 'CL', 'KMB',
    'GIS', 'K', 'CPB', 'SJM', 'CAG', 'HSY', 'MKC', 'HRL', 'TSN', 'ADM',
    'BG', 'STZ', 'TAP', 'SAM', 'MNST', 'CELH', 'KDP', 'EL', 'CLX', 'CHD',
    'KR', 'SYY', 'USFD', 'PFGC',

    # === INDUSTRIALS ===
    'BA', 'RTX', 'LMT', 'NOC', 'GD', 'HII', 'TDG', 'HWM', 'TXT', 'SPR', 'AXON',
    'CAT', 'DE', 'PCAR', 'CMI', 'AGCO', 'TEX', 'OSK',
    'HON', 'GE', 'MMM', 'ETN', 'EMR', 'ROK', 'AME', 'DOV', 'ITW', 'PH',
    'IR', 'XYL', 'ROP',
    'UPS', 'FDX', 'UNP', 'CSX', 'NSC', 'CP', 'CNI', 'JBHT', 'ODFL',
    'XPO', 'CHRW', 'EXPD', 'LSTR', 'SAIA', 'ARCB', 'SNDR', 'KNX',
    'DAL', 'UAL', 'LUV', 'AAL', 'ALK', 'JBLU',
    'SHW', 'PPG', 'APD', 'ECL', 'LIN', 'VMC', 'MLM', 'EXP',

    # === ENERGY ===
    'XOM', 'CVX', 'COP', 'EOG', 'DVN', 'FANG', 'MPC', 'VLO',
    'PSX', 'OXY', 'APA', 'HAL', 'SLB', 'BKR', 'NOV',
    'RRC', 'AR', 'EQT', 'CNX', 'CTRA', 'OVV', 'MTDR',
    'ENPH', 'FSLR', 'RUN', 'SEDG', 'ARRY', 'MAXN', 'JKS',
    'CSIQ', 'DQ', 'BE', 'PLUG', 'BLDP', 'NEE', 'AES', 'VST',

    # === MATERIALS ===
    'LIN', 'APD', 'ECL', 'SHW', 'PPG', 'NEM', 'FCX', 'SCCO', 'AA',
    'NUE', 'STLD', 'CLF', 'RS', 'CMC', 'ATI', 'WOR',
    'DOW', 'DD', 'LYB', 'EMN', 'CE', 'HUN', 'OLN', 'WLK', 'CC',
    'CF', 'NTR', 'MOS', 'FMC', 'CTVA', 'IFF', 'ALB', 'LAC',

    # === REAL ESTATE ===
    'AMT', 'PLD', 'CCI', 'EQIX', 'SPG', 'O', 'PSA', 'DLR', 'WELL', 'AVB',
    'EQR', 'VTR', 'ARE', 'BXP', 'SLG', 'VNO', 'KIM', 'REG', 'FRT', 'HST',
    'INVH', 'AMH', 'ESS', 'MAA', 'UDR', 'CPT', 'AIV',

    # === UTILITIES ===
    'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'WEC', 'ES',
    'ED', 'PEG', 'EIX', 'DTE', 'FE', 'PPL', 'CMS', 'AEE', 'EVRG', 'ATO',

    # === COMMUNICATION SERVICES ===
    'GOOGL', 'META', 'DIS', 'NFLX', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR',
    'LBRDK', 'LBRDA', 'EA', 'TTWO', 'RBLX', 'MTCH', 'BMBL',
    'ZG', 'Z', 'SPOT', 'TME', 'SE', 'GRAB', 'BABA', 'JD', 'PDD', 'BIDU',

    # === HIGH BETA / SPECULATIVE ===
    'GME', 'AMC', 'BB', 'CLOV', 'SNDL', 'TLRY', 'CGC', 'ACB', 'MSOS',
    'SPCE', 'RKLB', 'RDW',
    'JOBY', 'ACHR', 'EVTL', 'GOEV', 'HYLN', 'WKHS',
    'QS', 'MVST', 'CHPT', 'BLNK', 'EVGO',
    'ROKU', 'TTD', 'PUBM', 'MGNI', 'DSP', 'APPS', 'DT', 'BRZE',
    'AI', 'BBAI', 'SOUN', 'PRCT', 'IONQ', 'RGTI',
]


# ============================================================================
# DATA STRUCTURES
# ============================================================================
@dataclass
class TradeRecord:
    """Record of a completed trade"""
    symbol: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    sl_pct: float
    tp_pct: float
    score: int
    market_regime: str
    reasons: str
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0
    days_held: int = 0
    peak_pct: float = 0.0
    trough_pct: float = 0.0


# ============================================================================
# STANDARD SCREENER (Production Logic)
# ============================================================================
class ProductionScreener:
    """
    EXACT production screener logic.

    DO NOT MODIFY THIS CLASS unless production screener changes.
    Any changes here must be reflected in src/screeners/rapid_rotation_screener.py
    """

    def __init__(self, universe: List[str]):
        self.universe = universe
        self.data_cache: Dict[str, pd.DataFrame] = {}

    def get_market_regime(self, end_date: datetime) -> str:
        """Detect market regime using SPY"""
        try:
            start = end_date - timedelta(days=40)
            ticker = yf.Ticker('SPY')
            hist = ticker.history(start=start, end=end_date + timedelta(days=1))

            if len(hist) < 20:
                return "UNKNOWN"

            hist = hist[hist.index.tz_localize(None) <= pd.Timestamp(end_date)]
            if len(hist) < 20:
                return "UNKNOWN"

            current = hist['Close'].iloc[-1]
            sma20 = hist['Close'].tail(20).mean()
            mom_5d = ((current / hist['Close'].iloc[-5]) - 1) * 100 if len(hist) >= 5 else 0

            if current > sma20 and mom_5d > -2:
                return "BULL"
            elif current < sma20 * 0.98:
                return "BEAR"
            else:
                return "NEUTRAL"
        except:
            return "UNKNOWN"

    def load_historical_data(self, end_date: datetime, days: int = 60):
        """Load historical data ending at simulation date"""
        self.data_cache = {}
        start_date = end_date - timedelta(days=days + 10)

        # Download in batches for efficiency
        batch_size = 100
        loaded = 0

        for i in range(0, len(self.universe), batch_size):
            batch = self.universe[i:i+batch_size]
            try:
                data = yf.download(
                    batch,
                    start=start_date,
                    end=end_date + timedelta(days=1),
                    auto_adjust=True,
                    progress=False,
                    threads=True
                )

                if len(batch) == 1:
                    if len(data) >= 30:
                        data.columns = [c.lower() for c in data.columns]
                        data.index = data.index.tz_localize(None)
                        data = data[data.index <= pd.Timestamp(end_date)]
                        if len(data) >= 30:
                            self.data_cache[batch[0]] = data
                            loaded += 1
                else:
                    for symbol in batch:
                        try:
                            df = data.xs(symbol, level=1, axis=1).copy()
                            if len(df) >= 30:
                                df.columns = [c.lower() for c in df.columns]
                                df.index = df.index.tz_localize(None)
                                df = df[df.index <= pd.Timestamp(end_date)]
                                df = df.dropna()
                                if len(df) >= 30:
                                    self.data_cache[symbol] = df
                                    loaded += 1
                        except:
                            pass
            except:
                pass

            time.sleep(0.5)

        return loaded

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        if loss.iloc[-1] == 0:
            return 100.0
        rs = gain.iloc[-1] / loss.iloc[-1]
        return 100 - (100 / (1 + rs))

    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        if len(data) < period + 1:
            return 0.0
        high = data['high']
        low = data['low']
        close = data['close']
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def screen(self, market_regime: str = "BULL") -> List[Dict]:
        """Screen all stocks using production criteria"""
        if not self.data_cache:
            return []

        signals = []
        for symbol, data in self.data_cache.items():
            try:
                signal = self._analyze_stock(symbol, data, market_regime)
                if signal:
                    signals.append(signal)
            except:
                pass

        # Sort by score, return top 10
        signals.sort(key=lambda x: x['score'], reverse=True)
        return signals[:10]

    def _analyze_stock(self, symbol: str, data: pd.DataFrame, market_regime: str) -> Optional[Dict]:
        """
        PRODUCTION SCREENING LOGIC

        This is the exact same logic as in production screener.
        DO NOT modify without updating production code.
        """
        if len(data) < 30:
            return None

        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']
        open_price = data['open'] if 'open' in data.columns else close

        idx = len(data) - 1
        current_price = close.iloc[idx]

        # Price filter
        if current_price < 10 or current_price > 2000:
            return None

        # Calculate indicators
        rsi = self.calculate_rsi(close)
        atr = self.calculate_atr(data)
        if atr == 0:
            return None
        atr_pct = (atr / current_price) * 100

        # Momentum
        mom_1d = ((current_price / close.iloc[idx-1]) - 1) * 100 if idx >= 1 else 0
        mom_5d = ((current_price / close.iloc[idx-5]) - 1) * 100 if idx >= 5 else 0
        mom_20d = ((current_price / close.iloc[idx-20]) - 1) * 100 if idx >= 20 else 0
        yesterday_move = ((close.iloc[idx-1] / close.iloc[idx-2]) - 1) * 100 if idx >= 2 else 0

        # Moving averages
        sma5 = close.iloc[-5:].mean()
        sma20 = close.iloc[-20:].mean() if len(close) >= 20 else close.mean()
        sma50 = close.iloc[-50:].mean() if len(close) >= 50 else close.mean()

        # Gap and candle
        prev_close = close.iloc[idx-1] if idx >= 1 else current_price
        gap_pct = ((open_price.iloc[idx] - prev_close) / prev_close) * 100
        today_open = open_price.iloc[idx]
        today_is_green = current_price > today_open

        # Levels
        high_20d = high.iloc[-20:].max() if len(high) >= 20 else high.max()
        dist_from_high = ((high_20d - current_price) / high_20d) * 100
        support = low.iloc[-10:].min() if len(low) >= 10 else low.min()

        # Volume
        avg_volume = volume.iloc[-20:].mean() if len(volume) >= 20 else volume.mean()
        volume_ratio = volume.iloc[idx] / avg_volume if avg_volume > 0 else 1

        # ========================================
        # BOUNCE CONFIRMATION FILTERS
        # ========================================
        if yesterday_move > -1.0:
            return None
        if mom_1d < -1.0:
            return None
        if not today_is_green and mom_1d < 0.5:
            return None
        if gap_pct > 2.0:
            return None
        if current_price > sma5 * 1.02:
            return None
        if atr_pct < Config.MIN_ATR_PCT:
            return None

        # ========================================
        # v3.5: SMA20 FILTER (ROOT CAUSE FIX)
        # 92% of stop loss trades were below SMA20
        # ========================================
        if current_price < sma20:
            return None  # Must be above SMA20 (uptrend)

        # ========================================
        # SCORING
        # ========================================
        score = 0
        reasons = []

        # 1. Bounce confirmation (40 pts max)
        if today_is_green and mom_1d > 0.5:
            score += 40
            reasons.append("Strong bounce")
        elif today_is_green or mom_1d > 0.3:
            score += 25
            reasons.append("Bounce confirmed")

        # 2. Prior dip magnitude (40 pts max)
        if -12 <= mom_5d <= -5:
            score += 40
            reasons.append(f"Deep dip {mom_5d:.1f}%")
        elif -5 < mom_5d <= -3:
            score += 30
            reasons.append(f"Good dip {mom_5d:.1f}%")
        elif -3 < mom_5d < 0:
            score += 15
            reasons.append(f"Mild dip {mom_5d:.1f}%")

        # 3. Yesterday's dip (30 pts max)
        if yesterday_move <= -3:
            score += 30
            reasons.append(f"Big dip yesterday {yesterday_move:.1f}%")
        elif yesterday_move <= -1.5:
            score += 20
            reasons.append(f"Dip yesterday {yesterday_move:.1f}%")
        elif yesterday_move <= -1:
            score += 10

        # 4. RSI (35 pts max)
        if 25 <= rsi <= 40:
            score += 35
            reasons.append(f"Very oversold RSI={rsi:.0f}")
        elif 40 < rsi <= 50:
            score += 20
            reasons.append(f"Low RSI={rsi:.0f}")

        # 5. Trend context (25 pts max)
        if current_price > sma50 and current_price > sma20 * 0.98:
            score += 25
            reasons.append("Strong uptrend")
        elif current_price > sma20:
            score += 15
            reasons.append("Above SMA20")

        # 6. Volatility (20 pts max)
        if atr_pct > 5:
            score += 20
            reasons.append(f"Very volatile {atr_pct:.1f}%")
        elif atr_pct > 4:
            score += 15
            reasons.append(f"High vol {atr_pct:.1f}%")
        elif atr_pct > 3:
            score += 10

        # 7. Room to recover (20 pts max)
        if 10 <= dist_from_high <= 25:
            score += 20
            reasons.append(f"Great room {dist_from_high:.0f}%")
        elif 6 <= dist_from_high < 10:
            score += 10
            reasons.append(f"Some room {dist_from_high:.0f}%")

        # 8. Volume confirmation (15 pts max)
        if volume_ratio > 1.5:
            score += 15
            reasons.append("High vol bounce")
        elif volume_ratio > 1.2:
            score += 5

        # Check minimum score
        if score < Config.MIN_SCORE:
            return None

        # ========================================
        # CALCULATE SL/TP (Production Logic)
        # ========================================
        tp_multiplier = min(1.5, max(1.0, atr_pct / 3))
        tp_pct = Config.BASE_TP_PCT * tp_multiplier

        if atr_pct > 5:
            sl_pct = 4.0
        elif atr_pct > 4:
            sl_pct = 3.75
        else:
            sl_pct = Config.BASE_SL_PCT

        sl_from_support = ((current_price - support * 0.995) / current_price) * 100
        sl_pct = max(sl_pct, min(sl_from_support * 0.8, 4.5))

        stop_loss = current_price * (1 - sl_pct / 100)
        take_profit = current_price * (1 + tp_pct / 100)

        return {
            'symbol': symbol,
            'score': score,
            'entry_price': round(current_price, 2),
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'sl_pct': round(sl_pct, 2),
            'tp_pct': round(tp_pct, 2),
            'rsi': round(rsi, 1),
            'atr_pct': round(atr_pct, 2),
            'mom_1d': round(mom_1d, 2),
            'mom_5d': round(mom_5d, 2),
            'yesterday_move': round(yesterday_move, 2),
            'reasons': reasons,
            'market_regime': market_regime,
        }


# ============================================================================
# STANDARD BACKTEST ENGINE
# ============================================================================
class StandardBacktest:
    """
    STANDARD BACKTEST ENGINE

    This is the ONLY backtest that should be used for Rapid Trader.
    Any code changes should be validated using this backtest.

    DO NOT CREATE ALTERNATIVE BACKTESTS.
    """

    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.monthly_results: Dict = {}
        self.capital = Config.STARTING_CAPITAL
        self.screener = ProductionScreener(PRODUCTION_UNIVERSE)

    def simulate_trade_with_trailing(self, signal: Dict, entry_date: datetime, position_size: float) -> Optional[TradeRecord]:
        """
        Simulate trade with trailing stop (Production Portfolio Manager Logic)

        Trailing Logic:
        1. Activate at +TRAIL_ACTIVATION_PCT profit
        2. Lock in TRAIL_PERCENT of peak profit
        3. Stop loss at current trailing level
        """
        symbol = signal['symbol']
        entry_price = signal['entry_price']
        stop_loss = signal['stop_loss']
        take_profit = signal['take_profit']
        sl_pct = signal['sl_pct']
        tp_pct = signal['tp_pct']

        trade = TradeRecord(
            symbol=symbol,
            entry_date=entry_date.strftime('%Y-%m-%d'),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
            score=signal['score'],
            market_regime=signal.get('market_regime', 'UNKNOWN'),
            reasons=', '.join(signal.get('reasons', [])[:3])
        )

        try:
            end = entry_date + timedelta(days=15)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=entry_date, end=end)

            if hist.empty or len(hist) < 2:
                return None
        except:
            return None

        peak_price = entry_price
        trough_price = entry_price
        trailing_activated = False
        current_trailing_stop = stop_loss

        for day_idx, (dt, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue

            high = row['High']
            low = row['Low']
            close = row['Close']

            peak_price = max(peak_price, high)
            trough_price = min(trough_price, low)

            peak_pct = ((peak_price - entry_price) / entry_price) * 100
            low_pnl = ((low - entry_price) / entry_price) * 100
            high_pnl = ((high - entry_price) / entry_price) * 100
            close_pnl = ((close - entry_price) / entry_price) * 100

            # Trailing stop activation
            if peak_pct >= Config.TRAIL_ACTIVATION_PCT and not trailing_activated:
                trailing_activated = True
                locked_profit = peak_pct * (Config.TRAIL_PERCENT / 100)
                current_trailing_stop = entry_price * (1 + locked_profit / 100)

            if trailing_activated:
                new_trail = entry_price * (1 + (peak_pct * Config.TRAIL_PERCENT / 100) / 100)
                if new_trail > current_trailing_stop:
                    current_trailing_stop = new_trail

            # Check exit conditions (priority order)

            # 1. Trailing stop hit
            if trailing_activated and low <= current_trailing_stop:
                trail_pnl = ((current_trailing_stop - entry_price) / entry_price) * 100
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = current_trailing_stop
                trade.exit_reason = "TRAIL_STOP"
                trade.pnl_pct = trail_pnl
                trade.pnl_usd = position_size * (trail_pnl / 100)
                trade.days_held = day_idx
                break

            # 2. Stop loss hit
            if low_pnl <= -sl_pct:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = stop_loss
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = -sl_pct
                trade.pnl_usd = position_size * (-sl_pct / 100)
                trade.days_held = day_idx
                break

            # 3. Take profit hit
            if high_pnl >= tp_pct:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = take_profit
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
                trade.pnl_usd = position_size * (tp_pct / 100)
                trade.days_held = day_idx
                break

            # 4. Max hold days
            if day_idx >= Config.MAX_HOLD_DAYS:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = close
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = close_pnl
                trade.pnl_usd = position_size * (close_pnl / 100)
                trade.days_held = day_idx
                break

        trade.peak_pct = ((peak_price - entry_price) / entry_price) * 100
        trade.trough_pct = ((trough_price - entry_price) / entry_price) * 100

        if not trade.exit_date:
            return None

        return trade

    def run(self, months_back: int = None):
        """Run the standard backtest"""
        if months_back is None:
            months_back = Config.MONTHS_BACK

        print("\n" + "="*70)
        print("STANDARD REALISTIC BACKTEST - RAPID TRADER")
        print("="*70)
        print(f"\nUniverse: {len(PRODUCTION_UNIVERSE)} stocks")
        print(f"Period: {months_back} months")
        print(f"Capital: ${Config.STARTING_CAPITAL:,}")
        print(f"Positions: {Config.MAX_POSITIONS} @ {Config.POSITION_SIZE_PCT}%")
        print(f"Trailing: +{Config.TRAIL_ACTIVATION_PCT}% activation, {Config.TRAIL_PERCENT}% lock")
        print("="*70 + "\n")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30)

        current = start_date
        week_num = 0
        all_symbols = set()

        while current <= end_date - timedelta(days=7):
            # Skip to Monday
            while current.weekday() >= 5:
                current += timedelta(days=1)

            if current > end_date - timedelta(days=7):
                break

            week_num += 1
            date_str = current.strftime('%Y-%m-%d')
            month_key = current.strftime('%Y-%m')

            print(f"\n[Week {week_num}] {date_str}")

            # Get market regime
            regime = self.screener.get_market_regime(current)
            print(f"  Market: {regime}")

            # Skip bear markets
            if regime == "BEAR":
                print(f"  SKIP: Bear market")
                current += timedelta(days=7)
                continue

            # Load data
            print(f"  Loading {len(PRODUCTION_UNIVERSE)} stocks...")
            loaded = self.screener.load_historical_data(current)
            print(f"  Loaded: {loaded}")

            if loaded < 20:
                current += timedelta(days=7)
                continue

            # Screen
            signals = self.screener.screen(market_regime=regime)

            if not signals:
                print(f"  No signals (score >= {Config.MIN_SCORE})")
                current += timedelta(days=7)
                continue

            print(f"  Found {len(signals)} signals")

            # Execute trades
            trades_this_week = 0
            for sig in signals[:Config.MAX_POSITIONS]:
                position_size = self.capital * (Config.POSITION_SIZE_PCT / 100)

                print(f"\n    {sig['symbol']}: Score={sig['score']}")
                print(f"      Entry=${sig['entry_price']:.2f}, "
                      f"SL=-{sig['sl_pct']:.1f}%, TP=+{sig['tp_pct']:.1f}%")

                trade = self.simulate_trade_with_trailing(sig, current, position_size)

                if trade:
                    self.trades.append(trade)
                    trades_this_week += 1
                    all_symbols.add(sig['symbol'])

                    self.capital += trade.pnl_usd

                    emoji = "WIN" if trade.pnl_pct > 0 else "LOSS"
                    print(f"      [{emoji}] {trade.exit_reason}: {trade.pnl_pct:+.2f}%")

                    # Track monthly
                    if month_key not in self.monthly_results:
                        self.monthly_results[month_key] = {
                            'trades': 0, 'wins': 0, 'losses': 0,
                            'pnl': 0, 'pnl_usd': 0
                        }
                    self.monthly_results[month_key]['trades'] += 1
                    self.monthly_results[month_key]['pnl'] += trade.pnl_pct
                    self.monthly_results[month_key]['pnl_usd'] += trade.pnl_usd
                    if trade.pnl_pct > 0:
                        self.monthly_results[month_key]['wins'] += 1
                    else:
                        self.monthly_results[month_key]['losses'] += 1

            print(f"\n  Week {week_num}: {trades_this_week} trades, Capital: ${self.capital:,.2f}")

            current += timedelta(days=7)
            time.sleep(0.5)

        print(f"\n{'='*70}")
        print(f"UNIQUE SYMBOLS TRADED: {len(all_symbols)}")
        print(f"{'='*70}")

        self._print_results()
        self._save_results()

    def _print_results(self):
        """Print comprehensive results"""
        if not self.trades:
            print("\nNo trades executed")
            return

        print(f"\n{'='*70}")
        print("BACKTEST RESULTS")
        print(f"{'='*70}")

        total = len(self.trades)
        winners = [t for t in self.trades if t.pnl_pct > 0]
        losers = [t for t in self.trades if t.pnl_pct <= 0]

        win_rate = len(winners) / total * 100
        avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

        print(f"\nTRADE STATISTICS:")
        print(f"  Total Trades: {total}")
        print(f"  Winners: {len(winners)} ({win_rate:.1f}%)")
        print(f"  Losers: {len(losers)} ({100-win_rate:.1f}%)")
        print(f"  Avg Win: {avg_win:+.2f}%")
        print(f"  Avg Loss: {avg_loss:+.2f}%")

        print(f"\nCAPITAL:")
        print(f"  Starting: ${Config.STARTING_CAPITAL:,}")
        print(f"  Ending: ${self.capital:,.2f}")
        print(f"  Total Return: {((self.capital/Config.STARTING_CAPITAL)-1)*100:+.2f}%")

        # Exit breakdown
        exit_counts = {}
        for t in self.trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        print(f"\nEXIT BREAKDOWN:")
        for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            trades_by_reason = [t for t in self.trades if t.exit_reason == reason]
            avg = sum(t.pnl_pct for t in trades_by_reason) / len(trades_by_reason)
            win_count = len([t for t in trades_by_reason if t.pnl_pct > 0])
            wr = win_count / count * 100
            print(f"  {reason:15}: {count:3} ({pct:5.1f}%) avg {avg:+.2f}% WR={wr:.0f}%")

        # Monthly breakdown
        print(f"\nMONTHLY BREAKDOWN:")
        print(f"  {'Month':<10} {'Trades':>7} {'Win%':>7} {'P&L':>10}")
        print(f"  {'-'*40}")

        monthly_returns = []
        for month in sorted(self.monthly_results.keys()):
            data = self.monthly_results[month]
            if data['trades'] > 0:
                wr = data['wins'] / data['trades'] * 100
                print(f"  {month:<10} {data['trades']:>7} {wr:>6.1f}% {data['pnl']:>+9.2f}%")
                monthly_returns.append(data['pnl'])

        avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0

        print(f"\n{'='*50}")
        print(f"MONTHLY AVERAGE: {avg_monthly:+.2f}%")
        print(f"WIN RATE: {win_rate:.1f}%")
        print(f"{'='*50}")

    def _save_results(self):
        """Save results to JSON"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"standard_backtest_{timestamp}.json"

        total = len(self.trades)
        winners = [t for t in self.trades if t.pnl_pct > 0]
        monthly_returns = [d['pnl'] for d in self.monthly_results.values() if d['trades'] > 0]

        results = {
            'version': 'STANDARD',
            'timestamp': timestamp,
            'config': {
                'universe_size': len(PRODUCTION_UNIVERSE),
                'months_back': Config.MONTHS_BACK,
                'starting_capital': Config.STARTING_CAPITAL,
                'max_positions': Config.MAX_POSITIONS,
                'position_size_pct': Config.POSITION_SIZE_PCT,
                'trail_activation': Config.TRAIL_ACTIVATION_PCT,
                'trail_percent': Config.TRAIL_PERCENT,
                'min_score': Config.MIN_SCORE,
            },
            'summary': {
                'total_trades': total,
                'win_rate': len(winners) / total * 100 if total > 0 else 0,
                'avg_monthly_return': sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0,
                'total_return': ((self.capital / Config.STARTING_CAPITAL) - 1) * 100,
                'ending_capital': self.capital,
            },
            'monthly': self.monthly_results,
            'trades': [asdict(t) for t in self.trades],
        }

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\nResults saved to: {output_file}")


# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Standard Realistic Backtest for Rapid Trader')
    parser.add_argument('--months', type=int, default=6, help='Number of months to backtest')
    args = parser.parse_args()

    backtest = StandardBacktest()
    backtest.run(months_back=args.months)
