"""Canonical feature computation — single source of truth.

Used by BOTH trainer (backtests/feature_builder.py) and live (src/scan/strategies/ml_filter.py)
to ensure feature parity between backtest validation and production scoring.

Design principles:
  1. NO LOOKAHEAD — every feature uses only data available at signal time.
  2. Bar-aligned — intraday features computed at the exact 5-min boundary of the signal,
     not session aggregate.
  3. Adaptive baselines — vol_ratio, range_exp use per-stock rolling history,
     not hardcoded constants.

Each function takes raw inputs and returns a single feature value (or dict).
The caller (trainer or live) is responsible for assembling these into a feature dict
matching the model's expected feature_<bucket>.txt order.
"""
from __future__ import annotations

from typing import Optional, Sequence
import numpy as np


# ============================================================
# Bar-derived features (compute from intraday 5-min bars)
# ============================================================

def gain_from_open(cur_close: float, day_open: float) -> float:
    """% change from session open."""
    if day_open <= 0:
        return 0.0
    return (cur_close / day_open - 1) * 100


def range_pct(cum_high: float, cum_low: float, day_open: float) -> float:
    """Cumulative high-low range as % of open."""
    if day_open <= 0:
        return 0.0
    return (cum_high - cum_low) / day_open * 100


def from_peak_pct(cur_close: float, cum_high: float) -> float:
    """% below cumulative session high."""
    if cum_high <= 0:
        return 0.0
    return (cur_close / cum_high - 1) * 100


def vs_vwap(cur_close: float, vwap: float) -> float:
    """% above/below VWAP. VWAP must be HLC/3 weighted (Alpaca standard).

    Caller computes VWAP using:
      vwap = sum((h+l+c)/3 * v) / sum(v)
    """
    if vwap <= 0:
        return 0.0
    return (cur_close / vwap - 1) * 100


def compute_vwap_hlc(bars) -> float:
    """HLC/3-weighted VWAP. bars = sequence of (time, open, high, low, close, volume)."""
    if not bars:
        return 0.0
    num = 0.0
    den = 0.0
    for b in bars:
        h, l, c, v = b[2], b[3], b[4], b[5]
        if v is None or v <= 0:
            continue
        typical = (h + l + c) / 3
        num += typical * v
        den += v
    return num / den if den > 0 else 0.0


def vol_ratio(today_cum_vol_at_time: float, baseline_cum_vol_at_time: float) -> float:
    """Today's cumulative volume up to signal time vs same-time-of-day baseline.

    Canonical: today_vol / 30-day-avg-vol-at-same-time-of-day.
    Caller pre-computes baseline as rolling avg of cumulative vol at this mfo.

    Returns 0 if baseline missing (treat as no signal).
    Caps at 20 to avoid extreme outliers dominating.
    """
    if baseline_cum_vol_at_time <= 0:
        return 0.0
    return min(20.0, today_cum_vol_at_time / baseline_cum_vol_at_time)


def vol_accel(past_bars) -> float:
    """Recent volume vs prior volume within session.

    Compares last 3 bars' volume to the prior 3 bars' volume.
    Stable, locally meaningful (no session-baseline dependence).
    Returns 1.0 if insufficient bars.
    """
    if len(past_bars) < 6:
        return 1.0
    recent = sum((b[5] or 0) for b in past_bars[-3:])
    prior = sum((b[5] or 0) for b in past_bars[-6:-3])
    if prior <= 0:
        return 1.0
    return min(20.0, recent / prior)


def bars_since_hi(past_bars) -> int:
    """Bars since cumulative session high.

    First-occurrence definition: peak_idx = first bar that reaches the running max.
    Returns 0 if peak is current bar.
    """
    if not past_bars:
        return 0
    peak_h = -float('inf')
    peak_idx = 0
    for i, b in enumerate(past_bars):
        if b[2] > peak_h:
            peak_h = b[2]
            peak_idx = i
    return len(past_bars) - 1 - peak_idx


def hh_count(past_bars) -> int:
    """Count of bars that made new cumulative session highs."""
    count = 0
    prev_hi = -float('inf')
    for b in past_bars:
        if b[2] > prev_hi:
            count += 1
            prev_hi = b[2]
    return count


def consol(past_bars, day_open: float, window: int = 5) -> float:
    """Range of last `window` bars as % of day_open.

    Lower = tighter consolidation = potential setup.
    """
    if not past_bars or day_open <= 0:
        return 0.0
    last = past_bars[-min(window, len(past_bars)):]
    hi = max(b[2] for b in last)
    lo = min(b[3] for b in last)
    return (hi - lo) / day_open * 100


def range_exp(range_pct_today: float, range_pct_baseline_10d: float) -> float:
    """Range expansion ratio: today's range vs 10-day rolling avg range.

    >1 = expanding (volatile day), <1 = compressing.
    Falls back to 1.0 if baseline missing.
    """
    if range_pct_baseline_10d <= 0:
        return 1.0
    return range_pct_today / range_pct_baseline_10d


def gap_from_prev(day_open: float, prev_close: float) -> float:
    """Overnight gap %."""
    if prev_close <= 0:
        return 0.0
    return (day_open / prev_close - 1) * 100


# ============================================================
# Daily-derived features (use stock's daily OHLC history)
# ============================================================

def mom_d(closes: Sequence[float], days: int) -> float:
    """N-day momentum % (most recent close vs N days ago)."""
    if len(closes) < days + 1 or closes[-(days + 1)] <= 0:
        return 0.0
    return (closes[-1] / closes[-(days + 1)] - 1) * 100


def dist_sma(closes: Sequence[float], window: int) -> float:
    """Distance from N-day SMA, %."""
    if len(closes) < window:
        return 0.0
    sma = float(np.mean(closes[-window:]))
    if sma <= 0:
        return 0.0
    return (closes[-1] / sma - 1) * 100


def pct_52w(cur_close: float, daily_closes_window: Sequence[float], side: str) -> float:
    """% above 52-week low or below 52-week high.

    side = 'hi' returns (close/52w_high - 1)*100  (typically negative)
    side = 'lo' returns (close/52w_low - 1)*100   (typically positive)
    Window: 250 trading days (Wall Street standard).
    """
    if not daily_closes_window:
        return 0.0
    win = list(daily_closes_window)[-250:]
    if not win:
        return 0.0
    ref = max(win) if side == 'hi' else min(win)
    if ref <= 0:
        return 0.0
    return (cur_close / ref - 1) * 100


# ============================================================
# Macro features (use macro_snapshots / breadth)
# ============================================================

def vix_5d_chg(vix_today: float, vix_5d_ago: float) -> float:
    """VIX absolute change over 5 trading days. Caller fetches OFFSET 5 (5 days back)."""
    if vix_5d_ago is None or vix_today is None:
        return 0.0
    return float(vix_today) - float(vix_5d_ago)


def macro_5d_pct(today_val: float, val_5d_ago: float) -> float:
    """Generic 5-day % change for BTC/JPY etc."""
    if not val_5d_ago or val_5d_ago == 0:
        return 0.0
    return (today_val / val_5d_ago - 1) * 100


def vix_term_spread(vix3m: float, vix: float) -> float:
    """VIX3M - VIX (positive = contango = healthy market)."""
    if vix3m is None or vix is None:
        return 1.5
    return float(vix3m) - float(vix)


# ============================================================
# Cross-asset (ETF intraday)
# ============================================================

def etf_intra_pct(etf_session_open: float, etf_close_at_time: float) -> float:
    """% change of ETF from session open to current bar time. Bar-aligned.

    Caller fetches:
      - ETF 09:30 open (etf_session_open)
      - ETF close at signal's 5-min bar (etf_close_at_time)
    """
    if etf_session_open <= 0:
        return 0.0
    return (etf_close_at_time / etf_session_open - 1) * 100


# ============================================================
# Quality interactions (used by 09:30 v21 model)
# ============================================================

def gain_x_spy(gain: float, spy_intra_v: float) -> float:
    return gain * spy_intra_v


def vol_x_mcap(vol_ratio_v: float, mcap_bucket_v: float) -> float:
    return vol_ratio_v * mcap_bucket_v


def gain_x_xlk(gain: float, xlk_intra_v: float) -> float:
    return gain * xlk_intra_v


def gain_div_vix(gain: float, vix: float) -> float:
    if vix <= 0:
        return 0.0
    return gain / (vix / 20.0)


def range_pullback(range_pct_v: float, gain: float) -> float:
    """High range + low gain = pullback opportunity."""
    return range_pct_v * (5 - max(0.0, min(5.0, gain)))


def sec_rel_strength(gain: float, sec_3d: float) -> float:
    """Stock's gain vs sector 3-day strength, clipped."""
    return float(np.clip(gain - sec_3d, -20.0, 20.0))


# ============================================================
# Misc
# ============================================================

def mcap_bucket(market_cap: float) -> int:
    """Market cap quintile (0=micro, 4=mega)."""
    if market_cap >= 100e9:
        return 4
    if market_cap >= 20e9:
        return 3
    if market_cap >= 5e9:
        return 2
    if market_cap >= 500e6:
        return 1
    return 0


def anomaly_score_zscore(etf_returns_at_time: dict, baseline_means: dict, baseline_stds: dict) -> float:
    """Sum of |z-scores| of ETF intraday returns vs rolling baseline.

    etf_returns_at_time: {etf_sym: pct_change_from_open_at_signal_time}
    baseline_means/stds: {etf_sym: rolling_mean / rolling_std at this mfo}
    """
    score = 0.0
    for etf, ret in etf_returns_at_time.items():
        m = baseline_means.get(etf)
        s = baseline_stds.get(etf)
        if m is None or s is None or s <= 0:
            continue
        score += abs((ret - m) / s)
    return score
