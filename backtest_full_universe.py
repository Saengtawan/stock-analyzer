#!/usr/bin/env python3
"""
Full Universe Backtest v1.0
============================
Uses all 987 stocks from full_universe_cache.json.
Applies daily pre-filter (same as pre_filter.py) each day dynamically.
Includes SPY regime + sector ETF scoring + slippage/commission.

This is the most realistic backtest possible.
"""
import sys, os, json, time
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from screeners.rapid_trader_filters import (
    check_bounce_confirmation, check_sma20_filter,
    calculate_dynamic_sl_tp, calculate_score,
)
from config.strategy_config import RapidRotationConfig

# ========================================
# CONFIG
# ========================================
START        = '2023-01-01'
END          = '2025-12-31'
DATA_START   = '2022-10-01'   # warmup for indicators
SLIPPAGE     = 0.20
COMMISSION   = 0.10
COST         = SLIPPAGE + COMMISSION

# Pre-filter thresholds (from pre_filter.py)
MIN_PRICE         = 5.0
MIN_ATR_PCT       = 2.3
MAX_OVEREXT_PCT   = 10.0
MAX_RSI           = 70.0
MIN_DOLLAR_VOL    = 5_000_000
MIN_DIP_5D        = -1.0
MAX_DIP_5D        = -15.0

# Screener config
cfg = RapidRotationConfig.from_yaml('config/trading.yaml')
MIN_SCORE    = cfg.min_score
MAX_HOLD     = cfg.max_hold_days
MAX_POSITIONS = cfg.max_positions
NORM_SIZE    = cfg.position_size_pct / 100
BEAR_SIZE    = cfg.bear_position_size_pct / 100

# SPY/Sector regime
REGIME_SMA   = 20
SECTOR_BULL  = 3.0
SECTOR_BEAR  = -3.0

SECTOR_ETFS = {
    'Technology': 'XLK', 'Communication Services': 'XLC',
    'Consumer Cyclical': 'XLY', 'Financial Services': 'XLF',
    'Energy': 'XLE', 'Healthcare': 'XLV', 'Industrials': 'XLI',
    'Basic Materials': 'XLB', 'Real Estate': 'XLRE',
    'Consumer Defensive': 'XLP', 'Utilities': 'XLU',
}

# ========================================
# LOAD UNIVERSE
# ========================================
universe_data = json.load(open('data/full_universe_cache.json'))
all_symbols = [s for s, v in universe_data.items()
               if isinstance(v, dict) and v.get('status') == 'active']
sector_map = {s: v.get('sector', 'Unknown') for s, v in universe_data.items()}
print(f"Universe: {len(all_symbols)} active stocks")

# ========================================
# DOWNLOAD ALL DATA IN BATCHES
# ========================================
def download_batch(symbols, start, end, batch_size=80):
    all_data = {}
    batches = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}/{len(batches)} ({len(batch)} stocks)...", flush=True)
        try:
            raw = yf.download(batch, start=start, end=end,
                              progress=False, auto_adjust=True, group_by='ticker')
            if len(batch) == 1:
                sym = batch[0]
                if not raw.empty:
                    all_data[sym] = raw
            else:
                for sym in batch:
                    try:
                        if sym in raw.columns.get_level_values(0):
                            df = raw[sym].dropna(how='all')
                            if len(df) > 50:
                                all_data[sym] = df
                    except:
                        pass
        except Exception as e:
            print(f"  Batch error: {e}")
        time.sleep(0.3)
    return all_data

print("\nDownloading SPY + sector ETFs...")
etf_symbols = list(set(SECTOR_ETFS.values())) + ['SPY']
etf_raw = yf.download(etf_symbols, start=DATA_START, end=END,
                      progress=False, auto_adjust=True, group_by='ticker')
spy_close = etf_raw['SPY']['Close'].squeeze()
etf_close = {}
for etf in set(SECTOR_ETFS.values()):
    try:
        etf_close[etf] = etf_raw[etf]['Close'].squeeze()
    except:
        pass
print(f"  SPY: {len(spy_close)} days, ETFs: {len(etf_close)} loaded")

print(f"\nDownloading {len(all_symbols)} universe stocks...")
stock_data = download_batch(all_symbols, DATA_START, END, batch_size=80)
print(f"  Loaded: {len(stock_data)}/{len(all_symbols)} stocks\n")

# ========================================
# HELPERS
# ========================================
def spy_is_bull(date):
    try:
        idx = spy_close.index.get_indexer([date], method='pad')[0]
        if idx < REGIME_SMA:
            return False
        sma = spy_close.iloc[idx-REGIME_SMA+1:idx+1].mean()
        return float(spy_close.iloc[idx]) > float(sma)
    except:
        return False

def sector_regime(sector, date):
    etf = SECTOR_ETFS.get(sector)
    if not etf or etf not in etf_close:
        return 'SIDEWAYS'
    try:
        close = etf_close[etf]
        idx = close.index.get_indexer([date], method='pad')[0]
        if idx < 20:
            return 'SIDEWAYS'
        ret = (float(close.iloc[idx]) / float(close.iloc[idx-20]) - 1) * 100
        if ret > SECTOR_BULL:
            return 'BULL'
        if ret < SECTOR_BEAR:
            return 'BEAR'
        return 'SIDEWAYS'
    except:
        return 'SIDEWAYS'

def pre_filter_check(symbol, df, idx):
    try:
        if idx < 50:
            return False
        close = float(df['Close'].iloc[idx])
        if close < MIN_PRICE:
            return False

        hi = df['High'].iloc[idx-14:idx+1]
        lo = df['Low'].iloc[idx-14:idx+1]
        cl_prev = df['Close'].iloc[idx-15:idx]
        tr = pd.concat([hi - lo,
                        (hi - cl_prev.values).abs(),
                        (lo - cl_prev.values).abs()], axis=1).max(axis=1)
        atr_pct = tr.mean() / close * 100
        if atr_pct < MIN_ATR_PCT:
            return False

        sma20 = float(df['Close'].iloc[idx-19:idx+1].mean())
        pct_from_sma20 = (close - sma20) / sma20 * 100
        if pct_from_sma20 < 0:
            return False
        if pct_from_sma20 > MAX_OVEREXT_PCT:
            return False

        delta = df['Close'].diff()
        gain = delta.clip(lower=0).iloc[idx-13:idx+1].mean()
        loss = (-delta.clip(upper=0)).iloc[idx-13:idx+1].mean()
        rsi = float(100 - (100 / (1 + gain/loss))) if loss > 0 else 100.0
        if rsi > MAX_RSI:
            return False

        avg_vol = float(df['Volume'].iloc[idx-19:idx+1].mean())
        if close * avg_vol < MIN_DOLLAR_VOL:
            return False

        if idx >= 5:
            ret5 = (close / float(df['Close'].iloc[idx-5]) - 1) * 100
            if ret5 > MIN_DIP_5D:
                return False
            if ret5 < MAX_DIP_5D:
                return False

        return True
    except:
        return False

def calc_indicators(df, idx):
    try:
        close = float(df['Close'].iloc[idx])
        hi = df['High']
        lo = df['Low']
        vol = df['Volume']
        cl = df['Close']

        tr_vals = pd.concat([hi - lo,
            (hi - cl.shift(1)).abs(),
            (lo - cl.shift(1)).abs()], axis=1).max(axis=1)
        atr_pct = float(tr_vals.iloc[idx-4:idx+1].mean()) / close * 100
        sma5  = float(cl.iloc[idx-4:idx+1].mean())
        sma20 = float(cl.iloc[idx-19:idx+1].mean())
        sma50 = float(cl.iloc[max(0,idx-49):idx+1].mean())
        avg_vol20 = float(vol.iloc[idx-19:idx+1].mean())
        vol_ratio = float(vol.iloc[idx]) / avg_vol20 if avg_vol20 > 0 else 1.0
        delta = cl.diff()
        gain = delta.clip(lower=0).iloc[idx-13:idx+1].mean()
        loss = (-delta.clip(upper=0)).iloc[idx-13:idx+1].mean()
        rsi = float(100 - (100 / (1 + gain/loss))) if loss > 0 else 50.0
        mom1d  = float((cl.iloc[idx] / cl.iloc[idx-1] - 1) * 100) if idx >= 1 else 0
        mom5d  = float((cl.iloc[idx] / cl.iloc[idx-5] - 1) * 100) if idx >= 5 else 0
        mom20d = float((cl.iloc[idx] / cl.iloc[idx-20] - 1) * 100) if idx >= 20 else 0
        high20 = float(hi.iloc[idx-19:idx+1].max())
        dist_from_high = float((close - high20) / high20 * 100)
        yesterday_move = float((cl.iloc[idx-1] / cl.iloc[idx-2] - 1) * 100) if idx >= 2 else 0
        today_open = float(df['Open'].iloc[idx])
        today_is_green = close > today_open
        gap_pct = float((today_open / float(cl.iloc[idx-1]) - 1) * 100) if idx >= 1 else 0
        swing_low_5d = float(lo.iloc[idx-4:idx+1].min())
        ema5 = float(cl.ewm(span=5, adjust=False).mean().iloc[idx])
        high52w = float(hi.iloc[max(0,idx-251):idx+1].max())

        return {
            'current_price': close, 'sma5': sma5, 'sma20': sma20, 'sma50': sma50,
            'atr_pct': atr_pct, 'rsi': rsi,
            'mom_1d': mom1d, 'mom_5d': mom5d, 'mom_20d': mom20d,
            'volume_ratio': vol_ratio, 'dist_from_high': dist_from_high,
            'yesterday_move': yesterday_move, 'today_is_green': today_is_green,
            'gap_pct': gap_pct, 'swing_low_5d': swing_low_5d,
            'ema5': ema5, 'high_20d': high20, 'high_52w': high52w,
        }
    except:
        return None

# ========================================
# MAIN BACKTEST LOOP
# ========================================
print(f"{'='*60}")
print(f"FULL UNIVERSE BACKTEST (987 stocks, daily pre-filter)")
print(f"Period: {START} to {END}")
print(f"{'='*60}\n")

trading_days = pd.date_range(start=START, end=END, freq='B')
active = {}
all_trades = []
daily_pool_sizes = []
skipped_bear_bear = 0
spy_bull_days = 0
spy_bear_days = 0

for day_num, current_date in enumerate(trading_days):
    date_str = current_date.strftime('%Y-%m-%d')

    is_bull = spy_is_bull(current_date)
    pos_size = NORM_SIZE if is_bull else BEAR_SIZE
    if is_bull:
        spy_bull_days += 1
    else:
        spy_bear_days += 1

    # --- CHECK EXITS ---
    to_close = []
    for sym, pos in list(active.items()):
        if sym not in stock_data:
            continue
        df = stock_data[sym]
        try:
            i = df.index.get_indexer([date_str], method='pad')[0]
            entry_i = df.index.get_indexer([pos['entry_date']], method='pad')[0]
            days_held = i - entry_i
        except:
            continue
        if i >= len(df):
            continue
        # Skip exit on entry day itself (just filled at open)
        if days_held <= 0:
            continue

        day_low   = float(df['Low'].iloc[i])
        day_high  = float(df['High'].iloc[i])
        day_close = float(df['Close'].iloc[i])

        exited = False
        if day_low <= pos['stop_loss']:
            entry_p = pos['entry_price']
            actual_pnl = (pos['stop_loss'] - entry_p) / entry_p * 100 - COST
            all_trades.append({**pos, 'exit_date': date_str, 'pnl_pct': actual_pnl,
                               'reason': 'SL', 'days': days_held, 'symbol': sym})
            exited = True
        elif day_high >= pos['take_profit']:
            entry_p = pos['entry_price']
            actual_pnl = (pos['take_profit'] - entry_p) / entry_p * 100 - COST
            all_trades.append({**pos, 'exit_date': date_str, 'pnl_pct': actual_pnl,
                               'reason': 'TP', 'days': days_held, 'symbol': sym})
            exited = True
        elif days_held >= MAX_HOLD:
            entry_p = pos['entry_price']
            pnl = (day_close - entry_p) / entry_p * 100 - COST
            all_trades.append({**pos, 'exit_date': date_str, 'pnl_pct': pnl,
                               'reason': 'MaxHold', 'days': days_held, 'symbol': sym})
            exited = True
        if exited:
            to_close.append(sym)

    for sym in to_close:
        del active[sym]

    if len(active) >= MAX_POSITIONS:
        continue

    # --- SCAN NEW SIGNALS ---
    day_pool = []
    for sym in all_symbols:
        if sym in active:
            continue
        if sym not in stock_data:
            continue
        df = stock_data[sym]
        try:
            idx = df.index.get_indexer([date_str], method='pad')[0]
        except:
            continue
        if idx < 50:
            continue

        # 1. Daily pre-filter
        if not pre_filter_check(sym, df, idx):
            continue

        # 2. Sector regime
        sec = sector_map.get(sym, 'Unknown')
        sec_reg = sector_regime(sec, current_date)
        if not is_bull and sec_reg == 'BEAR':
            skipped_bear_bear += 1
            continue

        # 3. Indicators
        ind = calc_indicators(df, idx)
        if not ind:
            continue

        # 4. Bounce confirmation
        passed, _ = check_bounce_confirmation(
            yesterday_move=ind['yesterday_move'],
            mom_1d=ind['mom_1d'],
            today_is_green=ind['today_is_green'],
            gap_pct=ind['gap_pct'],
            current_price=ind['current_price'],
            sma5=ind['sma5'],
            atr_pct=ind['atr_pct'],
        )
        if not passed:
            continue

        # 5. SMA20 filter
        passed, _ = check_sma20_filter(ind['current_price'], ind['sma20'])
        if not passed:
            continue

        # 6. Score
        score, _ = calculate_score(
            today_is_green=ind['today_is_green'],
            mom_1d=ind['mom_1d'],
            mom_5d=ind['mom_5d'],
            yesterday_move=ind['yesterday_move'],
            rsi=ind['rsi'],
            current_price=ind['current_price'],
            sma20=ind['sma20'],
            sma50=ind['sma50'],
            atr_pct=ind['atr_pct'],
            dist_from_high=ind['dist_from_high'],
            volume_ratio=ind['volume_ratio'],
        )
        if score < MIN_SCORE:
            continue

        # 7. SL/TP
        sl_tp = calculate_dynamic_sl_tp(
            current_price=ind['current_price'],
            atr=ind['atr_pct'] / 100 * ind['current_price'],
            swing_low_5d=ind['swing_low_5d'],
            ema5=ind['ema5'],
            high_20d=ind['high_20d'],
            high_52w=ind['high_52w'],
        )
        day_pool.append({'symbol': sym, 'score': score, 'sector': sec,
                         'ind': ind, 'sl_tp': sl_tp, 'idx': idx})

    daily_pool_sizes.append(len(day_pool))

    # Top signals by score
    day_pool.sort(key=lambda x: -x['score'])
    for sig in day_pool:
        if len(active) >= MAX_POSITIONS:
            break
        sym = sig['symbol']
        if sym in active:
            continue

        # Entry = NEXT DAY OPEN (realistic execution)
        df = stock_data[sym]
        next_idx = sig['idx'] + 1
        if next_idx >= len(df):
            continue
        entry_price = float(df['Open'].iloc[next_idx])
        entry_date_actual = df.index[next_idx].strftime('%Y-%m-%d')

        # Recalculate SL/TP from actual entry price
        sl_tp2 = calculate_dynamic_sl_tp(
            current_price=entry_price,
            atr=sig['ind']['atr_pct'] / 100 * entry_price,
            swing_low_5d=sig['ind']['swing_low_5d'],
            ema5=sig['ind']['ema5'],
            high_20d=sig['ind']['high_20d'],
            high_52w=sig['ind']['high_52w'],
        )
        sl_pct = sl_tp2['sl_pct']
        tp_pct = sl_tp2['tp_pct']

        active[sym] = {
            'entry_date': entry_date_actual,   # actual next-day entry date
            'entry_price': entry_price,         # actual next-day open
            'stop_loss': entry_price * (1 - sl_pct/100),
            'take_profit': entry_price * (1 + tp_pct/100),
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'pos_size': pos_size,
            'spy_regime': 'BULL' if is_bull else 'BEAR',
            'sector': sig['sector'],
            'score': sig['score'],
        }

    if day_num % 60 == 0:
        print(f"  {date_str}: signals={len(day_pool)}, active={len(active)}, trades={len(all_trades)}", flush=True)

# ========================================
# RESULTS
# ========================================
df_trades = pd.DataFrame(all_trades)
df_trades.to_csv('backtest_3yr_full_universe.csv', index=False)

CAP = 25000
total = len(df_trades)
print(f"\n{'='*60}")
print(f"RESULTS: Full Universe Backtest (987 stocks, daily pre-filter)")
print(f"{'='*60}")

if total == 0:
    print("No trades generated!")
else:
    winners = df_trades[df_trades['pnl_pct'] > 0]
    losers  = df_trades[df_trades['pnl_pct'] <= 0]

    print(f"Total Trades:        {total}")
    print(f"Win Rate:            {len(winners)/total*100:.1f}%")
    print(f"Avg Win:             +{winners['pnl_pct'].mean():.2f}%")
    print(f"Avg Loss:            {losers['pnl_pct'].mean():.2f}%")
    print(f"Avg P&L/trade:       {df_trades['pnl_pct'].mean():+.2f}%")
    print(f"Avg daily signals:   {np.mean(daily_pool_sizes):.1f}")
    print(f"SPY BULL/BEAR days:  {spy_bull_days}/{spy_bear_days}")
    print(f"Skipped BEAR+BEAR:   {skipped_bear_bear}")

    df_trades['exit_date'] = pd.to_datetime(df_trades['exit_date'])
    df_trades['month'] = df_trades['exit_date'].dt.to_period('M')
    df_trades['dollar_pnl'] = df_trades['pnl_pct'] / 100 * df_trades['pos_size'] * CAP

    monthly = df_trades.groupby('month').agg(
        trades=('pnl_pct', 'count'),
        wins=('pnl_pct', lambda x: (x > 0).sum()),
        dollar=('dollar_pnl', 'sum'),
    )
    monthly['win_pct'] = monthly['wins'] / monthly['trades'] * 100
    monthly['port_pct'] = monthly['dollar'] / CAP * 100

    print(f"\nMONTHLY")
    print(f"{'Month':<10} {'Tr':>4} {'Win%':>6} {'Port%':>8} {'$25k':>9}")
    print('-'*45)
    for m, r in monthly.iterrows():
        print(f"{str(m):<10} {r['trades']:>4.0f} {r['win_pct']:>5.1f}% {r['port_pct']:>+7.2f}% ${r['dollar']:>+8,.0f}")

    print(f"\nANNUAL")
    for year in ['2023', '2024', '2025']:
        yr = monthly[monthly.index.astype(str).str.startswith(year)]
        avg_m = yr['port_pct'].mean()
        prof = (yr['port_pct'] > 0).sum()
        total_dollar = yr['dollar'].sum()
        print(f"{year}: avg={avg_m:+.2f}%/month  profitable={prof}/12  total=${total_dollar:+,.0f}")

    # Drawdown
    daily_pnl = df_trades.groupby('exit_date')['dollar_pnl'].sum()
    days_range = pd.date_range(START, END, freq='B')
    eq = pd.Series(0.0, index=days_range)
    eq.update(daily_pnl)
    equity = CAP + eq.cumsum()
    dd = (equity - equity.cummax()) / equity.cummax() * 100

    avg_mo = monthly['port_pct'].mean()
    print(f"\nSUMMARY")
    print(f"Max Drawdown:        {dd.min():.2f}%  (${(equity - equity.cummax()).min():,.0f})")
    print(f"Total Return 3yr:    {(equity.iloc[-1]/CAP-1)*100:.1f}%")
    print(f"CAGR:                {((equity.iloc[-1]/CAP)**(1/3)-1)*100:.1f}%")
    print(f"Avg monthly return:  {avg_mo:+.2f}%  => ${CAP * avg_mo / 100:,.0f}/month on $25k")
