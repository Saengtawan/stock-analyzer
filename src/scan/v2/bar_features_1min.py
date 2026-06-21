"""
v2 L0 — bar-feature builder from Alpaca IEX 1-min (the live-faithful source).

Proven by L0 POC (2026-06-18): IEX 1-min reconstruction matches the LIVE snapshot
bit-exact on range/hi/lo features (median Δ 0.000) and ~0.2 on open-derived features
(gain/from_peak/vs_vwap — the irreducible thin-09:30-open ambiguity). vs the current
training pkl which is ~0.6 off the live source → this cuts train/serve skew ~3x and
to ~0 for range features.

USE for BOTH:
  - rebuild the training feature pkl (bar block) from IEX 1-min  → train == serve source
  - (optionally) live serve, replacing the snapshot dailyBar bar features

Macro/daily features are NOT here (they come from DB tables, already parity-clean P2/P5).
For true 0-parity on open features long-term: accumulate live snapshots forward and
retrain on them. This module is the best historical proxy.
"""
from __future__ import annotations
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo('America/New_York')


def _hdr():
    return {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY') or os.getenv('APCA_API_KEY_ID'),
            'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY') or os.getenv('APCA_API_SECRET_KEY')}


def fetch_1min(syms, date, feed='iex'):
    """IEX 1-min bars (feed='iex' matches the live snapshot). Returns {sym: [bars]}."""
    out, hdr = {}, _hdr()
    for i in range(0, len(syms), 100):
        p = {'feed': feed, 'symbols': ','.join(syms[i:i+100]), 'timeframe': '1Min',
             'start': f'{date}T13:30:00Z', 'end': f'{date}T20:05:00Z', 'limit': 10000}
        r = requests.get('https://data.alpaca.markets/v2/stocks/bars', headers=hdr, params=p, timeout=30)
        if r.status_code == 200:
            out.update(r.json().get('bars', {}))
    return out


def _etmin(t):
    d = datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(ET)
    return d.hour * 60 + d.minute


def bar_features(bars, mfo, prev_close=None, avg_range_10d=None, avg_daily_vol=None):
    """Compute the cumulative bar-feature block at minutes-from-open=mfo.

    bars: list of 1-min bars (Alpaca, with o/h/l/c/v/vw). Returns None if no data.
    prev_close/avg_range_10d/avg_daily_vol: from daily DB (for gap/range_exp/vol_ratio).
    """
    cutoff = 9 * 60 + 30 + mfo
    b = [x for x in bars if _etmin(x['t']) <= cutoff]
    if len(b) < 1:
        return None
    o = b[0]['o']
    if o <= 0:
        return None
    hi = max(x['h'] for x in b); lo = min(x['l'] for x in b); c = b[-1]['c']
    tv = sum(x['v'] for x in b) or 1
    vw = sum(x['v'] * x.get('vw', x['c']) for x in b) / tv
    closes = [x['c'] for x in b]
    # bar-pattern features
    hh = sum(1 for i in range(1, len(b)) if b[i]['h'] > b[i-1]['h'])
    peak_i = max(range(len(b)), key=lambda i: b[i]['h'])
    bars_since_hi = len(b) - 1 - peak_i
    rng = (hi - lo) / o * 100
    f = {
        'gain_from_open': (c / o - 1) * 100,
        'range_pct': rng,
        'from_peak_pct': (c / hi - 1) * 100 if hi > 0 else 0.0,
        'vs_vwap': (c / vw - 1) * 100 if vw > 0 else 0.0,
        'hh_count': hh,
        'bars_since_hi': bars_since_hi,
        'consol': (max(closes) - min(closes)) / o * 100,
    }
    if prev_close and prev_close > 0:
        f['gap_from_prev'] = (o / prev_close - 1) * 100
    if avg_range_10d and avg_range_10d > 0:
        f['range_exp'] = rng / avg_range_10d
    if avg_daily_vol and avg_daily_vol > 0:
        frac = max(5, mfo + 5) / 390.0
        f['vol_ratio'] = min(20.0, sum(x['v'] for x in b) / (avg_daily_vol * frac))
    return f
