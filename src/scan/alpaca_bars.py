"""
Alpaca 5-min bars fetcher for live intraday feature extraction.

Fetches today's 5-min bars for a list of symbols, computes features
that require multi-bar context:
- bars_since_hi
- vol_accel (last 3 bars vs prior 3)
- hh_count (higher highs last 5 bars)
- consol (range of last 5 bars)
- consec_green
- pullback_depth
- slope_5, slope_10
- gain_first30

Used by ml_filter strategy during live scans.
"""
import os
import requests
from datetime import datetime, timedelta
import pytz
from typing import Dict, List

ET = pytz.timezone('US/Eastern')


def fetch_today_bars(symbols: List[str], timeframe: str = '5Min') -> Dict[str, List[dict]]:
    """Fetch today's intraday bars for all symbols (default 5Min; pass '1Min' for finer resolution
    — the riser capture-peak exit uses 1Min to lock closer to the intraday peak).

    Returns dict of {symbol: [bars_as_dict]} ordered by timestamp.
    Each bar has: t, o, h, l, c, v, n, vw
    """
    hdr = {
        'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'),
        'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY'),
    }
    now_et = datetime.now(ET)
    start_et = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    start = start_et.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    end = now_et.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')

    result = {}
    # Alpaca bars endpoint: up to 100 symbols per request
    for i in range(0, len(symbols), 100):
        batch = symbols[i:i+100]
        params = {
            'symbols': ','.join(batch),
            'timeframe': timeframe,
            'start': start,
            'end': end,
            'limit': 10000,
            'feed': 'sip',  # fallback to 'iex' if no sip access
        }
        try:
            r = requests.get(
                'https://data.alpaca.markets/v2/stocks/bars',
                headers=hdr, params=params, timeout=30,
            )
            if r.status_code == 200:
                data = r.json().get('bars', {})
                result.update(data)
            elif r.status_code == 403:
                # Retry with iex feed
                params['feed'] = 'iex'
                r = requests.get(
                    'https://data.alpaca.markets/v2/stocks/bars',
                    headers=hdr, params=params, timeout=30,
                )
                if r.status_code == 200:
                    data = r.json().get('bars', {})
                    result.update(data)
        except Exception as e:
            print(f"  bar fetch error batch {i}: {e}")
    return result


def extract_multibar_features(bars: list, day_open: float) -> dict:
    """Compute features that require multi-bar context.

    Args:
        bars: list of bar dicts ordered by time
        day_open: first bar's open price

    Returns: dict of feature_name -> value
    """
    import numpy as np

    out = {
        'bars_since_hi': 0,
        'vol_accel': 1.0,
        'hh_count': 0,
        'consol': 0.0,
        'consec_green': 0,
        'pullback_depth': 0.0,
        'slope_5': 0.0,
        'slope_10': 0.0,
        'gain_first30': 0.0,
        'entry_vs_first30': 0.0,
        'time_since_peak': 0,
    }
    if not bars or day_open <= 0:
        return out

    n = len(bars)
    latest = bars[-1]
    ec = latest.get('c', 0)
    if ec <= 0:
        return out

    # Bars since cumulative session high — FIRST occurrence (canonical, matches trainer).
    peak_h = -float('inf')
    peak_idx = 0
    for i, b in enumerate(bars):
        h = b.get('h', 0)
        if h > peak_h:
            peak_h = h
            peak_idx = i
    out['bars_since_hi'] = (n - 1) - peak_idx
    out['time_since_peak'] = out['bars_since_hi']
    hi_sofar = peak_h

    # hh_count — cumulative all-bar new highs (canonical, matches trainer).
    prev_hi = -float('inf')
    cnt = 0
    for b in bars:
        h = b.get('h', 0)
        if h > prev_hi:
            cnt += 1
            prev_hi = h
    out['hh_count'] = cnt

    # Consolidation: range of last up-to-5 bars as % of day_open. Use all bars when
    # <5 (matches trainer feature_builder.py `past_bars[-min(5,len):]`; was guarded
    # n>=5 → fed 0 on early bars, a Z1/early-Z2 train/serve skew). Parity fix 2026-05-30.
    last5 = bars[-min(5, n):]
    l5_hi = max(b.get('h', 0) for b in last5)
    l5_lo = min(b.get('l', 9e9) for b in last5)
    out['consol'] = (l5_hi - l5_lo) / day_open * 100 if day_open > 0 else 0

    # Consecutive green bars
    for i in range(n - 1, -1, -1):
        b = bars[i]
        if b.get('c', 0) > b.get('o', 0):
            out['consec_green'] += 1
        else:
            break

    # Vol acceleration (last 3 vs prior 3). cap 20 + 1.0-when-zero-denom matches
    # trainer feature_builder.py (was uncapped last3/max(prev3,1) → could feed
    # values >20 the model never saw in training). Parity fix 2026-05-30.
    if n >= 6:
        last3_v = sum(b.get('v', 0) for b in bars[-3:])
        prev3_v = sum(b.get('v', 0) for b in bars[-6:-3])
        out['vol_accel'] = min(20.0, last3_v / prev3_v) if prev3_v > 0 else 1.0

    # Pullback depth from peak
    if peak_idx < n - 1:
        lows_after = [b.get('l', 0) for b in bars[peak_idx:]]
        min_after = min(lows_after) if lows_after else ec
        out['pullback_depth'] = (min_after / hi_sofar - 1) * 100 if hi_sofar > 0 else 0

    # Slopes
    if n >= 3:
        xs = np.arange(min(5, n))
        ys = np.array([b.get('c', 0) for b in bars[-min(5, n):]])
        if len(ys) >= 2 and ec > 0:
            slope5 = np.polyfit(xs, ys, 1)[0]
            out['slope_5'] = slope5 / ec * 100

    if n >= 5:
        xs = np.arange(min(10, n))
        ys = np.array([b.get('c', 0) for b in bars[-min(10, n):]])
        if len(ys) >= 3 and ec > 0:
            slope10 = np.polyfit(xs, ys, 1)[0]
            out['slope_10'] = slope10 / ec * 100

    # First 30 min gain (find bar at ~10:00 by timestamp)
    first30_close = day_open
    for b in bars:
        t = b.get('t', '')
        # t format: "2026-04-10T14:00:00Z" = 10:00 ET
        if 'T14:00:00' in t:  # 10:00 ET = 14:00 UTC (summer) or 15:00 UTC (winter)
            first30_close = b.get('c', day_open)
            break
    out['gain_first30'] = (first30_close / day_open - 1) * 100 if day_open > 0 else 0
    out['entry_vs_first30'] = (ec / first30_close - 1) * 100 if first30_close > 0 else 0

    return out
