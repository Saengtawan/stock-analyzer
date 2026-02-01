#!/usr/bin/env python3
"""
REALISTIC BACKTEST v3.5 - IMPROVED DYNAMIC SL/TP

v3.5 Improvements:
1. ไม่ใช้ EMA5 สำหรับ entry SL (แคบเกินไป)
2. ใช้ ATR × 2 แทน ATR × 1.5 (ให้ room มากขึ้น)
3. MIN_SL = 3.5% (ไม่ให้ต่ำกว่า 3.5%)
4. Trailing activation = 4% (รอให้กำไรมากพอก่อน)
5. ใช้ 680+ หุ้นจาก S&P 500 + NASDAQ 100 + High-Beta

Period: 6 months (Jul 2025 - Jan 2026)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import yfinance as yf
import warnings
import json
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION v3.5
# ============================================================
START_DATE = datetime(2025, 7, 1)
END_DATE = datetime(2026, 1, 31)
INITIAL_CAPITAL = 10000
MAX_POSITIONS = 3
POSITION_SIZE_PCT = 0.30

# v3.5: IMPROVED SL/TP parameters
ATR_SL_MULTIPLIER = 2.0    # Wider (was 1.5)
ATR_TP_MULTIPLIER = 3.0
MIN_SL_PCT = 3.5           # Higher minimum (was 2.0)
MAX_SL_PCT = 8.0
MIN_TP_PCT = 5.0           # Higher minimum (was 4.0)
MAX_TP_PCT = 15.0

# v3.5: Trailing parameters
TRAIL_ACTIVATION_PCT = 4.0  # Higher (was 3.0)
ATR_TRAIL_MULTIPLIER = 1.5  # Tighter trailing once activated

# Screening parameters
MIN_SCORE = 85              # Slightly lower for more opportunities
MIN_ATR_PCT = 2.5


# ============================================================
# COMPREHENSIVE 680+ STOCK UNIVERSE
# ============================================================
FULL_UNIVERSE = [
    # === TECHNOLOGY (150+) ===
    # Mega Cap Tech
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA',
    # Semiconductors
    'AMD', 'AVGO', 'QCOM', 'TXN', 'INTC', 'MU', 'AMAT', 'LRCX', 'KLAC',
    'MRVL', 'ON', 'NXPI', 'ADI', 'MCHP', 'SWKS', 'QRVO', 'MPWR', 'ENTG',
    'TER', 'WOLF', 'CRUS', 'SLAB', 'RMBS', 'FORM', 'AOSL', 'POWI',
    'ARM', 'SMCI', 'TSM', 'ASML', 'SNPS', 'CDNS',
    # Software
    'CRM', 'ORCL', 'NOW', 'ADBE', 'INTU', 'SNOW', 'PLTR', 'DDOG', 'NET',
    'CRWD', 'ZS', 'PANW', 'FTNT', 'OKTA', 'ZM', 'DOCU', 'SPLK', 'TEAM',
    'WDAY', 'MDB', 'CFLT', 'PATH', 'S', 'HUBS', 'VEEV', 'ANSS', 'CDNS',
    'BILL', 'GTLB', 'ESTC', 'NEWR', 'SUMO', 'FIVN', 'TWLO', 'SNAP',
    # Internet/E-commerce
    'SHOP', 'PYPL', 'SQ', 'COIN', 'AFRM', 'UPST', 'HOOD', 'SOFI',
    'ABNB', 'UBER', 'LYFT', 'DASH', 'RBLX', 'U', 'MTTR', 'GLBE',
    # Hardware/Devices
    'DELL', 'HPQ', 'HPE', 'WDC', 'STX', 'NTAP',
    # Telecom/Communications
    'CSCO', 'JNPR', 'ANET', 'FFIV', 'AKAM', 'LLNW',

    # === HEALTHCARE (100+) ===
    # Pharma
    'JNJ', 'PFE', 'MRK', 'ABBV', 'LLY', 'BMY', 'AMGN', 'GILD', 'REGN',
    'VRTX', 'MRNA', 'BNTX', 'AZN', 'NVS', 'GSK', 'SNY', 'BIIB', 'ALNY',
    # Biotech
    'SGEN', 'BMRN', 'EXEL', 'INCY', 'SRPT', 'RARE', 'ALKS', 'IONS',
    'NBIX', 'UTHR', 'HALO', 'PCVX', 'ARWR', 'RETA', 'XENE', 'KRYS',
    'IMVT', 'RCKT', 'BEAM', 'EDIT', 'NTLA', 'CRSP', 'VERV',
    # Med Devices
    'ABT', 'MDT', 'SYK', 'BSX', 'EW', 'ISRG', 'DXCM', 'PODD', 'ALGN',
    'HOLX', 'IDXX', 'WAT', 'TMO', 'DHR', 'A', 'BIO', 'TECH', 'ILMN',
    # Healthcare Services
    'UNH', 'CVS', 'CI', 'HUM', 'CNC', 'MOH', 'ELV', 'HCA', 'THC',

    # === FINANCIALS (80+) ===
    # Banks
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'USB', 'PNC', 'TFC', 'COF',
    'AXP', 'SCHW', 'BK', 'STT', 'NTRS', 'FITB', 'KEY', 'RF', 'CFG',
    'HBAN', 'ZION', 'CMA', 'FRC', 'SIVB', 'WAL', 'PACW',
    # Insurance
    'BRK-B', 'PGR', 'TRV', 'ALL', 'AIG', 'MET', 'PRU', 'AFL', 'LNC',
    # Fintech/Payments
    'V', 'MA', 'FIS', 'FISV', 'GPN', 'ADP', 'PAYX', 'FLT', 'WU',
    # Asset Management
    'BLK', 'TROW', 'IVZ', 'BEN', 'NTRS', 'AMG', 'EV',

    # === CONSUMER DISCRETIONARY (80+) ===
    # Retail
    'HD', 'LOW', 'TGT', 'COST', 'WMT', 'TJX', 'ROST', 'BBY', 'DG', 'DLTR',
    'ULTA', 'FIVE', 'OLLI', 'BURL', 'WSM', 'RH', 'W', 'ETSY',
    # Apparel
    'NKE', 'LULU', 'UAA', 'VFC', 'PVH', 'RL', 'TPR', 'CPRI', 'GPS',
    # Restaurants
    'MCD', 'SBUX', 'CMG', 'DPZ', 'YUM', 'QSR', 'DNUT', 'WING', 'SHAK',
    'DRI', 'TXRH', 'EAT', 'CAKE', 'BLMN',
    # Auto
    'F', 'GM', 'RIVN', 'LCID', 'FSR', 'NKLA', 'XPEV', 'NIO', 'LI',
    'APTV', 'BWA', 'LEA', 'VC', 'ALV',
    # Hotels/Leisure
    'MAR', 'HLT', 'H', 'WH', 'CHH', 'LVS', 'WYNN', 'MGM', 'CZR',
    'RCL', 'CCL', 'NCLH', 'EXPE', 'BKNG', 'ABNB', 'TRIP', 'MTN',
    # Entertainment
    'DIS', 'NFLX', 'WBD', 'PARA', 'FOX', 'FOXA', 'LYV', 'MSGS',
    'CHWY', 'CHGG', 'PTON', 'FVRR', 'UPWK',

    # === CONSUMER STAPLES (40+) ===
    'PG', 'KO', 'PEP', 'PM', 'MO', 'COST', 'WMT', 'MDLZ', 'CL', 'KMB',
    'GIS', 'K', 'CPB', 'SJM', 'CAG', 'HSY', 'MKC', 'HRL', 'TSN', 'ADM',
    'BG', 'STZ', 'TAP', 'SAM', 'MNST', 'CELH', 'KDP', 'EL', 'CLX', 'CHD',
    'KR', 'SYY', 'USFD', 'PFGC', 'SPTN',

    # === INDUSTRIALS (80+) ===
    # Aerospace/Defense
    'BA', 'RTX', 'LMT', 'NOC', 'GD', 'HII', 'TDG', 'HWM', 'TXT', 'SPR',
    'ERJ', 'AXON',
    # Machinery
    'CAT', 'DE', 'PCAR', 'CMI', 'AGCO', 'CNHI', 'TEX', 'OSK',
    # Industrial Conglomerates
    'HON', 'GE', 'MMM', 'ETN', 'EMR', 'ROK', 'AME', 'DOV', 'ITW', 'PH',
    'IR', 'XYL', 'ROP',
    # Transportation
    'UPS', 'FDX', 'UNP', 'CSX', 'NSC', 'CP', 'CNI', 'JBHT', 'ODFL',
    'XPO', 'CHRW', 'EXPD', 'LSTR', 'SAIA', 'ARCB', 'SNDR', 'KNX',
    'DAL', 'UAL', 'LUV', 'AAL', 'ALK', 'JBLU', 'HA', 'SAVE',
    # Building/Construction
    'SHW', 'PPG', 'APD', 'ECL', 'LIN', 'VMC', 'MLM', 'EXP',

    # === ENERGY (50+) ===
    # Oil & Gas
    'XOM', 'CVX', 'COP', 'EOG', 'PXD', 'DVN', 'FANG', 'MPC', 'VLO',
    'PSX', 'OXY', 'HES', 'APA', 'MRO', 'HAL', 'SLB', 'BKR', 'NOV',
    'CHK', 'RRC', 'AR', 'EQT', 'SWN', 'CNX', 'CTRA', 'OVV', 'MTDR',
    # Clean Energy
    'ENPH', 'FSLR', 'RUN', 'SEDG', 'NOVA', 'ARRY', 'MAXN', 'JKS',
    'CSIQ', 'DQ', 'BE', 'PLUG', 'BLDP', 'BLOOM', 'NEE', 'AES', 'VST',

    # === MATERIALS (40+) ===
    'LIN', 'APD', 'ECL', 'SHW', 'PPG', 'NEM', 'FCX', 'SCCO', 'AA',
    'X', 'NUE', 'STLD', 'CLF', 'RS', 'CMC', 'ATI', 'WOR',
    'DOW', 'DD', 'LYB', 'EMN', 'CE', 'HUN', 'OLN', 'WLK', 'CC',
    'CF', 'NTR', 'MOS', 'FMC', 'CTVA', 'IFF', 'ALB', 'LTHM', 'LAC', 'PLL',

    # === REAL ESTATE (30+) ===
    'AMT', 'PLD', 'CCI', 'EQIX', 'SPG', 'O', 'PSA', 'DLR', 'WELL', 'AVB',
    'EQR', 'VTR', 'ARE', 'BXP', 'SLG', 'VNO', 'KIM', 'REG', 'FRT', 'HST',
    'INVH', 'AMH', 'ESS', 'MAA', 'UDR', 'CPT', 'AIV',

    # === UTILITIES (25+) ===
    'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'WEC', 'ES',
    'ED', 'PEG', 'EIX', 'DTE', 'FE', 'PPL', 'CMS', 'AEE', 'EVRG', 'ATO',

    # === COMMUNICATION SERVICES (30+) ===
    'GOOGL', 'META', 'DIS', 'NFLX', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR',
    'LBRDK', 'LBRDA', 'EA', 'ATVI', 'TTWO', 'RBLX', 'MTCH', 'BMBL',
    'ZG', 'Z', 'SPOT', 'TME', 'SE', 'GRAB', 'BABA', 'JD', 'PDD', 'BIDU',

    # === HIGH BETA / MEME / SPECULATIVE (50+) ===
    'GME', 'AMC', 'BB', 'BBBY', 'CLOV', 'WISH', 'SNDL', 'TLRY', 'CGC',
    'ACB', 'APHA', 'MSOS', 'SPCE', 'RKLB', 'ASTR', 'RDW', 'VORB',
    'JOBY', 'LILM', 'ACHR', 'EVTL', 'GOEV', 'HYLN', 'RIDE', 'WKHS',
    'MULN', 'FFIE', 'QS', 'MVST', 'CHPT', 'BLNK', 'EVGO', 'DCFC',
    'ROKU', 'TTD', 'PUBM', 'MGNI', 'IS', 'DSP', 'APPS', 'DT', 'BRZE',
    'AI', 'BBAI', 'SOUN', 'PRCT', 'IONQ', 'RGTI',
]


@dataclass
class Position:
    """Active position with dynamic tracking"""
    symbol: str
    entry_date: datetime
    entry_price: float
    shares: int
    initial_sl: float
    current_sl: float
    initial_tp: float
    current_tp: float
    highest_price: float
    trailing_active: bool
    sl_method: str
    tp_method: str


@dataclass
class Trade:
    """Completed trade record"""
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    shares: int
    pnl_pct: float
    pnl_usd: float
    exit_reason: str
    days_held: int
    sl_method: str
    tp_method: str


class RealisticBacktestV35:
    """Realistic backtest v3.5 with 680+ stocks"""

    def __init__(self):
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.capital = INITIAL_CAPITAL
        self.cash = INITIAL_CAPITAL
        self.daily_values: List[Dict] = []
        self.universe = FULL_UNIVERSE.copy()

    def load_all_data(self):
        """Load historical data for all symbols"""
        print(f"Loading historical data for {len(self.universe)} stocks...")
        start = START_DATE - timedelta(days=60)
        end = END_DATE + timedelta(days=5)

        loaded = 0
        failed = 0

        # Download in batches for efficiency
        batch_size = 50
        for i in range(0, len(self.universe), batch_size):
            batch = self.universe[i:i+batch_size]
            try:
                # Download batch
                data = yf.download(batch, start=start, end=end,
                                   auto_adjust=True, progress=False,
                                   threads=True, group_by='ticker')

                for symbol in batch:
                    try:
                        if len(batch) == 1:
                            df = data.copy()
                        else:
                            df = data[symbol].copy()

                        if df is not None and len(df) >= 30:
                            df.columns = [c.lower() for c in df.columns]
                            df = df.dropna()
                            if len(df) >= 30:
                                self.data_cache[symbol] = df
                                loaded += 1
                    except Exception as e:
                        failed += 1
            except Exception as e:
                failed += len(batch)

            # Progress
            if (i + batch_size) % 200 == 0:
                print(f"  Progress: {min(i+batch_size, len(self.universe))}/{len(self.universe)}")

        print(f"Loaded {loaded} symbols, failed {failed}")

    def get_data_until(self, symbol: str, date: datetime) -> Optional[pd.DataFrame]:
        """Get data up to specific date"""
        if symbol not in self.data_cache:
            return None
        df = self.data_cache[symbol]
        mask = df.index.date <= date.date()
        return df[mask].copy() if mask.any() else None

    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate all indicators"""
        if len(df) < 20:
            return {}

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = (atr / close.iloc[-1]) * 100

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1])) if loss.iloc[-1] != 0 else 50

        # Momentum
        mom_1d = (close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) >= 2 else 0
        mom_5d = (close.iloc[-1] / close.iloc[-5] - 1) * 100 if len(close) >= 5 else 0
        mom_20d = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0
        yesterday_move = (close.iloc[-2] / close.iloc[-3] - 1) * 100 if len(close) >= 3 else 0

        # MAs
        sma5 = close.rolling(5).mean().iloc[-1]
        sma20 = close.rolling(20).mean().iloc[-1]

        # Swing levels
        swing_low_5d = low.iloc[-5:].min()
        swing_low_10d = low.iloc[-10:].min()
        swing_high_20d = high.iloc[-20:].max()
        high_52w = high.max()

        # Candle
        today_open = df['open'].iloc[-1]
        today_close = close.iloc[-1]
        today_is_green = today_close > today_open

        # Volume
        avg_volume = volume.iloc[-20:].mean()
        volume_ratio = volume.iloc[-1] / avg_volume if avg_volume > 0 else 1

        return {
            'close': close.iloc[-1],
            'open': today_open,
            'atr': atr,
            'atr_pct': atr_pct,
            'rsi': rsi,
            'mom_1d': mom_1d,
            'mom_5d': mom_5d,
            'mom_20d': mom_20d,
            'yesterday_move': yesterday_move,
            'sma5': sma5,
            'sma20': sma20,
            'swing_low_5d': swing_low_5d,
            'swing_low_10d': swing_low_10d,
            'swing_high_20d': swing_high_20d,
            'high_52w': high_52w,
            'today_is_green': today_is_green,
            'volume_ratio': volume_ratio,
        }

    def screen_stock(self, symbol: str, date: datetime) -> Optional[Dict]:
        """Screen a stock using v3.5 logic"""
        df = self.get_data_until(symbol, date)
        if df is None or len(df) < 20:
            return None

        ind = self.calculate_indicators(df)
        if not ind:
            return None

        current_price = ind['close']
        atr = ind['atr']
        atr_pct = ind['atr_pct']

        # Skip penny stocks and illiquid
        if current_price < 5 or current_price > 1000:
            return None

        # ============ BOUNCE CONFIRMATION FILTERS ============
        # FILTER 1: Yesterday MUST be down
        if ind['yesterday_move'] > -1.0:
            return None

        # FILTER 2: Today should show recovery
        if ind['mom_1d'] < -1.0:
            return None

        # FILTER 3: Green candle preferred
        if not ind['today_is_green'] and ind['mom_1d'] < 0.5:
            return None

        # FILTER 4: Skip big gap ups
        gap_pct = (ind['open'] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
        if gap_pct > 2.0:
            return None

        # FILTER 5: Not too extended
        if current_price > ind['sma5'] * 1.02:
            return None

        # FILTER 6: Minimum volatility
        if atr_pct < MIN_ATR_PCT:
            return None

        # ============ SCORING ============
        score = 0
        reasons = []

        # Bounce confirmation
        if ind['today_is_green'] and ind['mom_1d'] > 0.5:
            score += 40
            reasons.append("Strong bounce")
        elif ind['today_is_green'] or ind['mom_1d'] > 0.3:
            score += 25
            reasons.append("Bounce")

        # Prior dip (5-day)
        if -12 <= ind['mom_5d'] <= -5:
            score += 40
            reasons.append(f"Deep dip")
        elif -5 < ind['mom_5d'] <= -3:
            score += 30
            reasons.append(f"Good dip")
        elif -3 < ind['mom_5d'] < 0:
            score += 15

        # Yesterday's dip
        if ind['yesterday_move'] <= -3:
            score += 30
        elif ind['yesterday_move'] <= -1.5:
            score += 20
        else:
            score += 10

        # RSI
        if 25 <= ind['rsi'] <= 40:
            score += 20
            reasons.append(f"Oversold")
        elif 40 < ind['rsi'] <= 50:
            score += 10

        # Volume spike
        if ind['volume_ratio'] > 1.5:
            score += 10
            reasons.append("High volume")

        # Check minimum score
        if score < MIN_SCORE:
            return None

        # ============ v3.5 DYNAMIC SL/TP ============

        # --- STOP LOSS (v3.5: NO EMA for entry, wider ATR) ---
        # Method 1: ATR-based (ATR × 2)
        atr_sl_distance = atr * ATR_SL_MULTIPLIER
        atr_based_sl = current_price - atr_sl_distance

        # Method 2: Swing Low based (10-day for more room)
        swing_low_sl = ind['swing_low_10d'] * 0.99  # 1% below swing low

        # Choose HIGHEST SL (but not EMA - too tight for entry)
        sl_options = {
            'ATR': atr_based_sl,
            'SwingLow': swing_low_sl,
        }
        sl_method = max(sl_options, key=sl_options.get)
        stop_loss = sl_options[sl_method]

        # Apply safety caps (v3.5: min 3.5%)
        sl_pct_raw = (current_price - stop_loss) / current_price * 100
        sl_pct = max(MIN_SL_PCT, min(sl_pct_raw, MAX_SL_PCT))
        stop_loss = current_price * (1 - sl_pct / 100)

        # --- TAKE PROFIT ---
        atr_based_tp = current_price + (atr * ATR_TP_MULTIPLIER)
        resistance_tp = ind['swing_high_20d'] * 0.995
        high_52w_tp = ind['high_52w'] * 0.98

        tp_options = {
            'ATR': atr_based_tp,
            'Resistance': resistance_tp,
            '52wHigh': high_52w_tp
        }
        tp_method = min(tp_options, key=tp_options.get)
        take_profit = tp_options[tp_method]

        # Apply safety caps (v3.5: min 5%)
        tp_pct_raw = (take_profit - current_price) / current_price * 100
        tp_pct = max(MIN_TP_PCT, min(tp_pct_raw, MAX_TP_PCT))
        take_profit = current_price * (1 + tp_pct / 100)

        # Risk/Reward check
        rr = tp_pct / sl_pct
        if rr < 1.2:
            return None  # Skip poor R/R

        return {
            'symbol': symbol,
            'score': score,
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'sl_method': sl_method,
            'tp_method': tp_method,
            'atr_pct': atr_pct,
            'rsi': ind['rsi'],
            'reasons': reasons
        }

    def calculate_dynamic_trailing(self, symbol: str, current_price: float,
                                   highest_price: float, date: datetime) -> Tuple[float, str]:
        """Calculate dynamic trailing SL (v3.5)"""
        df = self.get_data_until(symbol, date)
        if df is None or len(df) < 14:
            return highest_price * 0.96, 'fallback'

        close = df['close']
        high = df['high']
        low = df['low']

        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # v3.5: Tighter trailing once activated
        # Method 1: ATR-based (1.5x for trailing)
        atr_based_sl = highest_price - (atr * ATR_TRAIL_MULTIPLIER)

        # Method 2: Swing Low
        swing_low_5d = low.iloc[-5:].min()
        swing_low_sl = swing_low_5d * 0.995

        # Method 3: EMA (OK for trailing, not entry)
        ema5 = close.ewm(span=5).mean().iloc[-1]
        ema_based_sl = ema5 * 0.99

        # Choose highest
        sl_options = {'ATR': atr_based_sl, 'SwingLow': swing_low_sl, 'EMA': ema_based_sl}
        sl_method = max(sl_options, key=sl_options.get)
        new_sl = sl_options[sl_method]

        # Don't trail tighter than 2% from current
        min_distance = current_price * 0.02
        if current_price - new_sl < min_distance:
            new_sl = current_price - min_distance
            sl_method = 'MinDist'

        return new_sl, sl_method

    def run_backtest(self):
        """Run the full backtest"""
        print("=" * 70)
        print("REALISTIC BACKTEST v3.5 - IMPROVED DYNAMIC SL/TP")
        print("=" * 70)
        print(f"Period: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
        print(f"Universe: {len(self.universe)} stocks")
        print(f"Initial Capital: ${INITIAL_CAPITAL:,.0f}")
        print()
        print("v3.5 Parameters:")
        print(f"  ATR_SL_MULTIPLIER: {ATR_SL_MULTIPLIER} (was 1.5)")
        print(f"  MIN_SL_PCT: {MIN_SL_PCT}% (was 2.0%)")
        print(f"  TRAIL_ACTIVATION: {TRAIL_ACTIVATION_PCT}% (was 3.0%)")
        print()

        self.load_all_data()
        print()

        trading_days = pd.date_range(START_DATE, END_DATE, freq='B')
        monthly_results = {}
        current_month = None
        month_start_value = INITIAL_CAPITAL

        for date in trading_days:
            date_dt = date.to_pydatetime()
            month_key = date_dt.strftime('%Y-%m')

            if month_key != current_month:
                if current_month is not None:
                    month_end_value = self.get_portfolio_value(date_dt)
                    monthly_results[current_month] = {
                        'start': month_start_value,
                        'end': month_end_value,
                        'return_pct': (month_end_value / month_start_value - 1) * 100
                    }
                current_month = month_key
                month_start_value = self.get_portfolio_value(date_dt)

            # ============ CHECK POSITIONS ============
            positions_to_close = []

            for symbol, pos in self.positions.items():
                df = self.get_data_until(symbol, date_dt)
                if df is None or len(df) == 0:
                    continue

                current_price = df['close'].iloc[-1]
                high_today = df['high'].iloc[-1]
                low_today = df['low'].iloc[-1]
                days_held = (date_dt - pos.entry_date).days
                pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100

                exit_reason = None
                exit_price = current_price

                # Update highest and trailing
                if high_today > pos.highest_price:
                    pos.highest_price = high_today

                    if pnl_pct >= TRAIL_ACTIVATION_PCT:
                        pos.trailing_active = True
                        new_sl, sl_m = self.calculate_dynamic_trailing(
                            symbol, current_price, pos.highest_price, date_dt
                        )
                        if new_sl > pos.current_sl:
                            pos.current_sl = new_sl
                            pos.sl_method = f"Trail:{sl_m}"

                # Check exits
                if low_today <= pos.current_sl:
                    exit_reason = "TRAILING_SL" if pos.trailing_active else "STOP_LOSS"
                    exit_price = pos.current_sl
                elif high_today >= pos.current_tp:
                    exit_reason = "TAKE_PROFIT"
                    exit_price = pos.current_tp
                elif days_held >= 5 and pnl_pct < 1:
                    exit_reason = "TIME_STOP"
                    exit_price = current_price

                if exit_reason:
                    positions_to_close.append((symbol, exit_price, exit_reason, date_dt))

            for symbol, exit_price, exit_reason, exit_dt in positions_to_close:
                self.close_position(symbol, exit_price, exit_reason, exit_dt)

            # ============ SCAN FOR NEW (Monday) ============
            if date.dayofweek == 0 and len(self.positions) < MAX_POSITIONS:
                signals = []
                for symbol in self.data_cache.keys():
                    if symbol in self.positions:
                        continue
                    signal = self.screen_stock(symbol, date_dt)
                    if signal:
                        signals.append(signal)

                signals.sort(key=lambda x: x['score'], reverse=True)

                for signal in signals[:MAX_POSITIONS - len(self.positions)]:
                    self.open_position(signal, date_dt)

            # Record daily
            self.daily_values.append({
                'date': date_dt,
                'value': self.get_portfolio_value(date_dt),
                'positions': len(self.positions)
            })

        # Last month
        if current_month:
            month_end_value = self.get_portfolio_value(END_DATE)
            monthly_results[current_month] = {
                'start': month_start_value,
                'end': month_end_value,
                'return_pct': (month_end_value / month_start_value - 1) * 100
            }

        self.print_results(monthly_results)

    def open_position(self, signal: Dict, date: datetime):
        """Open a new position"""
        position_value = self.cash * POSITION_SIZE_PCT
        shares = int(position_value / signal['entry_price'])

        if shares < 1:
            return

        cost = shares * signal['entry_price']
        self.cash -= cost

        self.positions[signal['symbol']] = Position(
            symbol=signal['symbol'],
            entry_date=date,
            entry_price=signal['entry_price'],
            shares=shares,
            initial_sl=signal['stop_loss'],
            current_sl=signal['stop_loss'],
            initial_tp=signal['take_profit'],
            current_tp=signal['take_profit'],
            highest_price=signal['entry_price'],
            trailing_active=False,
            sl_method=signal['sl_method'],
            tp_method=signal['tp_method']
        )

        print(f"📈 {date.strftime('%Y-%m-%d')} BUY {signal['symbol']} x{shares} @ ${signal['entry_price']:.2f} "
              f"| SL:{signal['sl_method']}({signal['sl_pct']:.1f}%) TP:{signal['tp_method']}({signal['tp_pct']:.1f}%)")

    def close_position(self, symbol: str, exit_price: float, exit_reason: str, date: datetime):
        """Close a position"""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        proceeds = pos.shares * exit_price
        self.cash += proceeds

        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100
        pnl_usd = (exit_price - pos.entry_price) * pos.shares
        days_held = (date - pos.entry_date).days

        self.trades.append(Trade(
            symbol=symbol,
            entry_date=pos.entry_date,
            exit_date=date,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            shares=pos.shares,
            pnl_pct=pnl_pct,
            pnl_usd=pnl_usd,
            exit_reason=exit_reason,
            days_held=days_held,
            sl_method=pos.sl_method,
            tp_method=pos.tp_method
        ))

        emoji = "✅" if pnl_pct >= 0 else "❌"
        trail_info = f" (Trail: ${pos.initial_sl:.2f}→${pos.current_sl:.2f})" if pos.trailing_active else ""
        print(f"{emoji} {date.strftime('%Y-%m-%d')} SELL {symbol} @ ${exit_price:.2f} | {pnl_pct:+.1f}% | {exit_reason}{trail_info}")

        del self.positions[symbol]

    def get_portfolio_value(self, date: datetime) -> float:
        """Get total portfolio value"""
        value = self.cash
        for symbol, pos in self.positions.items():
            df = self.get_data_until(symbol, date)
            if df is not None and len(df) > 0:
                value += pos.shares * df['close'].iloc[-1]
        return value

    def print_results(self, monthly_results: Dict):
        """Print detailed results"""
        print()
        print("=" * 70)
        print("BACKTEST RESULTS")
        print("=" * 70)

        if self.trades:
            wins = [t for t in self.trades if t.pnl_pct > 0]
            losses = [t for t in self.trades if t.pnl_pct <= 0]

            print(f"\n📊 TRADE STATISTICS:")
            print(f"   Total Trades: {len(self.trades)}")
            print(f"   Winners: {len(wins)} ({len(wins)/len(self.trades)*100:.1f}%)")
            print(f"   Losers: {len(losses)} ({len(losses)/len(self.trades)*100:.1f}%)")

            if wins:
                print(f"   Avg Win: +{np.mean([t.pnl_pct for t in wins]):.2f}%")
            if losses:
                print(f"   Avg Loss: {np.mean([t.pnl_pct for t in losses]):.2f}%")

            print(f"   Avg Days Held: {np.mean([t.days_held for t in self.trades]):.1f}")

            # Profit factor
            total_wins = sum([t.pnl_usd for t in wins]) if wins else 0
            total_losses = abs(sum([t.pnl_usd for t in losses])) if losses else 1
            profit_factor = total_wins / total_losses if total_losses > 0 else 0
            print(f"   Profit Factor: {profit_factor:.2f}")

            print(f"\n📋 EXIT REASONS:")
            reasons = {}
            for t in self.trades:
                reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
            for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                pct = count / len(self.trades) * 100
                # Win rate for each reason
                wins_for_reason = len([t for t in self.trades if t.exit_reason == reason and t.pnl_pct > 0])
                wr = wins_for_reason / count * 100
                print(f"   {reason}: {count} ({pct:.1f}%) - Win Rate: {wr:.0f}%")

        # Monthly results
        print(f"\n📅 MONTHLY RETURNS:")
        print("-" * 50)
        total_months = 0
        positive_months = 0

        for month, data in sorted(monthly_results.items()):
            ret = data['return_pct']
            total_months += 1
            if ret > 0:
                positive_months += 1
            emoji = "✅" if ret > 0 else "❌"
            bar = "█" * int(abs(ret) * 2) if ret > 0 else "░" * int(abs(ret) * 2)
            print(f"   {month}: {emoji} {ret:+6.2f}% {bar}")

        print("-" * 50)
        avg_monthly = sum([d['return_pct'] for d in monthly_results.values()]) / total_months if total_months > 0 else 0
        print(f"   Average Monthly: {avg_monthly:+.2f}%")
        print(f"   Positive Months: {positive_months}/{total_months}")

        # Final
        final_value = self.get_portfolio_value(END_DATE)
        total_return_pct = (final_value / INITIAL_CAPITAL - 1) * 100

        print(f"\n💰 FINAL RESULTS:")
        print(f"   Initial Capital: ${INITIAL_CAPITAL:,.0f}")
        print(f"   Final Value: ${final_value:,.0f}")
        print(f"   Total Return: {total_return_pct:+.2f}%")

        # Save results
        results = {
            'version': 'v3.5',
            'period': f"{START_DATE.date()} to {END_DATE.date()}",
            'total_trades': len(self.trades),
            'win_rate': len([t for t in self.trades if t.pnl_pct > 0]) / len(self.trades) * 100 if self.trades else 0,
            'avg_monthly_return': avg_monthly,
            'total_return': total_return_pct,
            'trades': [
                {
                    'symbol': t.symbol,
                    'entry': t.entry_date.strftime('%Y-%m-%d'),
                    'exit': t.exit_date.strftime('%Y-%m-%d'),
                    'pnl_pct': round(t.pnl_pct, 2),
                    'exit_reason': t.exit_reason
                }
                for t in self.trades
            ]
        }

        with open('backtest_v35_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n📁 Results saved to backtest_v35_results.json")


if __name__ == "__main__":
    backtest = RealisticBacktestV35()
    backtest.run_backtest()
