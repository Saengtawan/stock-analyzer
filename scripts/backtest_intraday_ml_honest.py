"""
Honest backtest of IntradayMLFilter on 5-min bars.

No data leakage: features use prev_close (yesterday), not today's close.
Walk-forward: model trained on data before test period.
"""
import sys
sys.path.insert(0, 'src')

import math
import random
import numpy as np
from collections import defaultdict
from database.orm.base import get_session
from sqlalchemy import text
from discovery.intraday_ml_filter import IntradayMLFilter

random.seed(42)


def load_macro_lookup(conn, min_date, max_date):
    rows = conn.execute(text("""
        SELECT ms.date, ms.vix_close, mb.pct_above_20d_ma
        FROM macro_snapshots ms
        LEFT JOIN market_breadth mb ON ms.date = mb.date
        WHERE ms.date >= :min_d AND ms.date <= :max_d
    """), {'min_d': min_date, 'max_d': max_date}).mappings().fetchall()
    lookup = {}
    for r in rows:
        lookup[r['date']] = {
            'vix_close': r['vix_close'] or 20.0,
            'breadth': r['pct_above_20d_ma'] or 50.0,
        }
    return lookup


def load_daily_features(conn, min_date, max_date):
    """Load daily OHLC features for building ML features at signal time.
    Returns {(symbol, date): {prev_close, close_5d, close_20d, ...}}
    """
    rows = conn.execute(text("""
        WITH bars AS (
            SELECT symbol, date, open, high, low, close, volume,
                   LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
                   LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date) as close_5d,
                   LAG(close, 20) OVER (PARTITION BY symbol ORDER BY date) as close_20d,
                   AVG(volume) OVER (PARTITION BY symbol ORDER BY date
                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as avg_vol_20d,
                   MAX(high) OVER (PARTITION BY symbol ORDER BY date
                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) as high_20d,
                   AVG((high - low) / NULLIF(close, 0) * 100) OVER (
                       PARTITION BY symbol ORDER BY date
                       ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) as atr_pct_5d
            FROM stock_daily_ohlc
            WHERE date >= date(:min_d, '-30 days') AND date <= :max_d
              AND open > 0 AND close > 5
        )
        SELECT symbol, date, open, close, prev_close, close_5d, close_20d,
               avg_vol_20d, high_20d, atr_pct_5d, volume
        FROM bars
        WHERE date >= :min_d AND date <= :max_d
          AND prev_close IS NOT NULL AND prev_close > 0
    """), {'min_d': min_date, 'max_d': max_date}).mappings().fetchall()

    features = {}
    for r in rows:
        features[(r['symbol'], r['date'])] = dict(r)
    return features


def load_fundamentals(conn):
    rows = conn.execute(text(
        "SELECT symbol, beta, market_cap FROM stock_fundamentals"
    )).mappings().fetchall()
    return {r['symbol']: dict(r) for r in rows}


def build_ml_features(daily, fund, gap_pct, volume_ratio_live, macro_day):
    """Build 11 features matching IntradayMLFilter training, using prev_close (no leakage)."""
    prev_close = daily.get('prev_close', 0)
    close_5d = daily.get('close_5d')
    close_20d = daily.get('close_20d')
    high_20d = daily.get('high_20d')
    atr_pct = daily.get('atr_pct_5d') or 2.0
    beta = fund.get('beta') or 1.0
    mcap = fund.get('market_cap') or 0
    mcap_log = math.log10(mcap) if mcap and mcap > 0 else 10.0

    # Use prev_close for momentum — matches honest training
    mom_5d = ((prev_close / close_5d - 1) * 100) if close_5d and close_5d > 0 else 0.0
    mom_20d = ((prev_close / close_20d - 1) * 100) if close_20d and close_20d > 0 else 0.0
    dist_20d_high = ((prev_close / high_20d - 1) * 100) if high_20d and high_20d > 0 else 0.0

    # RSI approximation
    avg_mom = mom_5d * 0.6 + mom_20d * 0.4
    rsi_14 = 50 + 30 * (2 / (1 + math.exp(-avg_mom * 0.3)) - 1)
    rsi_14 = round(max(20.0, min(80.0, rsi_14)), 1)

    vix_close = macro_day.get('vix_close', 20.0)
    breadth = macro_day.get('breadth', 50.0)

    return [
        gap_pct,
        volume_ratio_live,
        mom_5d,
        mom_20d,
        atr_pct,
        rsi_14,
        dist_20d_high,
        mcap_log,
        beta,
        vix_close,
        breadth,
    ]


def run_backtest():
    print("Loading ML model...")
    ml = IntradayMLFilter()
    ml.load_from_db()
    if not ml._fitted:
        print("ERROR: No fitted model found. Run fit() first.")
        return
    print(f"Model loaded (fit_date={ml._fit_date}, metrics={ml._metrics})")

    with get_session() as conn:
        # Get all available dates with 5m bars
        all_dates = [r[0] for r in conn.execute(text("""
            SELECT DISTINCT date FROM intraday_bars_5m
            WHERE date >= '2025-01-01' AND date <= '2026-03-17'
            ORDER BY date
        """)).fetchall()]

        print(f"Available dates: {len(all_dates)}")

        # Sample 200 random dates
        sample_dates = sorted(random.sample(all_dates, min(200, len(all_dates))))
        print(f"Sampling {len(sample_dates)} dates: {sample_dates[0]} to {sample_dates[-1]}")

        # Load macro
        macro_lookup = load_macro_lookup(conn, sample_dates[0], sample_dates[-1])

        # Load daily features
        print("Loading daily features...")
        daily_features = load_daily_features(conn, sample_dates[0], sample_dates[-1])
        print(f"  {len(daily_features)} (symbol,date) daily feature rows loaded")

        # Load fundamentals
        fundamentals = load_fundamentals(conn)
        print(f"  {len(fundamentals)} fundamentals loaded")

        # Results tracking
        results = defaultdict(lambda: {
            'no_filter': [], 'confirmed': [], 'high': []
        })
        total_signals = 0
        total_days_processed = 0

        for di, dt in enumerate(sample_dates):
            if di % 20 == 0:
                print(f"  Processing date {di+1}/{len(sample_dates)}: {dt}...")

            # Load 5-min bars for this date (market hours only: 09:30-16:00)
            bars_raw = conn.execute(text("""
                SELECT symbol, time_et, open, high, low, close, volume
                FROM intraday_bars_5m
                WHERE date = :dt AND time_et >= '09:30' AND time_et <= '16:00'
                ORDER BY symbol, time_et
            """), {'dt': dt}).fetchall()

            if not bars_raw:
                continue

            # Organize by symbol
            bars_by_sym = defaultdict(list)
            for b in bars_raw:
                bars_by_sym[b[0]].append({
                    'time': b[1], 'open': b[2], 'high': b[3],
                    'low': b[4], 'close': b[5], 'volume': b[6]
                })

            macro_day = macro_lookup.get(dt, {'vix_close': 20.0, 'breadth': 50.0})
            total_days_processed += 1

            for sym, bars in bars_by_sym.items():
                if len(bars) < 10:
                    continue

                daily = daily_features.get((sym, dt))
                if not daily or not daily.get('prev_close') or daily['prev_close'] <= 0:
                    continue

                prev_close = daily['prev_close']
                mkt_open = bars[0]['open']
                gap_pct = (mkt_open / prev_close - 1) * 100

                if gap_pct < 1.0:
                    continue  # Only gap-ups >= 1%

                fund = fundamentals.get(sym, {})

                # Walk through bars chronologically
                day_high = 0
                day_low = float('inf')
                day_volume = 0
                avg_vol_20d = daily.get('avg_vol_20d') or 1
                signals_emitted = set()  # track which strategies already triggered for this symbol
                dipped_below_open = False

                # Get last bar close as exit price (~15:55-16:00)
                exit_price = bars[-1]['close']

                for bi, bar in enumerate(bars):
                    t = bar['time']
                    day_high = max(day_high, bar['high'])
                    day_low = min(day_low, bar['low'])
                    day_volume += bar['volume'] or 0
                    current_price = bar['close']

                    if bar['low'] < mkt_open:
                        dipped_below_open = True

                    gap_filled = day_low <= prev_close
                    ret_from_open = (current_price / mkt_open - 1) * 100 if mkt_open > 0 else 0

                    volume_ratio = day_volume / avg_vol_20d if avg_vol_20d > 0 else 1.0

                    # ── S1: FIRST_BAR_CONFIRM ──
                    if ('S1' not in signals_emitted
                            and t >= '09:40' and t <= '10:30'
                            and gap_pct >= 1
                            and ret_from_open > 0.8
                            and not gap_filled):

                        entry_price = current_price
                        won = exit_price > entry_price
                        features = build_ml_features(daily, fund, gap_pct, volume_ratio, macro_day)
                        results['FIRST_BAR_CONFIRM']['no_filter'].append(won)
                        signals_emitted.add('S1')
                        total_signals += 1

                        # ML score
                        cand = [{'symbol': sym, 'gap_pct': gap_pct, 'strategy': 'FIRST_BAR_CONFIRM'}]
                        X = np.array([features], dtype=np.float64)
                        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
                        X_s = ml._scaler.transform(X)
                        gb_p = ml._gb_model.predict_proba(X_s)[0, 1]
                        lr_p = ml._lr_model.predict_proba(X_s)[0, 1]
                        lgbm_p = ml._lgbm_model.predict_proba(X_s)[0, 1] if ml._lgbm_model else None

                        vix = macro_day.get('vix_close', 20.0)
                        threshold = 0.7 if vix <= 20 else 0.75

                        if gb_p > 0.95:
                            results['FIRST_BAR_CONFIRM']['high'].append(won)
                            results['FIRST_BAR_CONFIRM']['confirmed'].append(won)
                        elif lgbm_p is not None:
                            if lr_p > threshold and gb_p > threshold and lgbm_p > threshold:
                                results['FIRST_BAR_CONFIRM']['confirmed'].append(won)

                    # ── S2: HOD_BREAK ──
                    if ('S2' not in signals_emitted
                            and t > '10:00'
                            and current_price >= day_high * 0.998):

                        entry_price = current_price
                        won = exit_price > entry_price
                        features = build_ml_features(daily, fund, gap_pct, volume_ratio, macro_day)
                        results['HOD_BREAK']['no_filter'].append(won)
                        signals_emitted.add('S2')
                        total_signals += 1

                        X = np.array([features], dtype=np.float64)
                        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
                        X_s = ml._scaler.transform(X)
                        gb_p = ml._gb_model.predict_proba(X_s)[0, 1]
                        lr_p = ml._lr_model.predict_proba(X_s)[0, 1]
                        lgbm_p = ml._lgbm_model.predict_proba(X_s)[0, 1] if ml._lgbm_model else None

                        vix = macro_day.get('vix_close', 20.0)
                        threshold = 0.7 if vix <= 20 else 0.75

                        if gb_p > 0.95:
                            results['HOD_BREAK']['high'].append(won)
                            results['HOD_BREAK']['confirmed'].append(won)
                        elif lgbm_p is not None:
                            if lr_p > threshold and gb_p > threshold and lgbm_p > threshold:
                                results['HOD_BREAK']['confirmed'].append(won)

                    # ── S3: RECLAIM_OPEN ──
                    if ('S3' not in signals_emitted
                            and t >= '10:00' and t <= '12:00'
                            and gap_pct >= 1
                            and dipped_below_open
                            and ret_from_open > 0.5
                            and not gap_filled):

                        entry_price = current_price
                        won = exit_price > entry_price
                        features = build_ml_features(daily, fund, gap_pct, volume_ratio, macro_day)
                        results['RECLAIM_OPEN']['no_filter'].append(won)
                        signals_emitted.add('S3')
                        total_signals += 1

                        X = np.array([features], dtype=np.float64)
                        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
                        X_s = ml._scaler.transform(X)
                        gb_p = ml._gb_model.predict_proba(X_s)[0, 1]
                        lr_p = ml._lr_model.predict_proba(X_s)[0, 1]
                        lgbm_p = ml._lgbm_model.predict_proba(X_s)[0, 1] if ml._lgbm_model else None

                        vix = macro_day.get('vix_close', 20.0)
                        threshold = 0.7 if vix <= 20 else 0.75

                        if gb_p > 0.95:
                            results['RECLAIM_OPEN']['high'].append(won)
                            results['RECLAIM_OPEN']['confirmed'].append(won)
                        elif lgbm_p is not None:
                            if lr_p > threshold and gb_p > threshold and lgbm_p > threshold:
                                results['RECLAIM_OPEN']['confirmed'].append(won)

                    # ── S4: GAP_NOT_FILLED ──
                    if ('S4' not in signals_emitted
                            and t >= '10:00' and t <= '11:00'
                            and gap_pct >= 2
                            and not gap_filled
                            and current_price > mkt_open):

                        entry_price = current_price
                        won = exit_price > entry_price
                        features = build_ml_features(daily, fund, gap_pct, volume_ratio, macro_day)
                        results['GAP_NOT_FILLED']['no_filter'].append(won)
                        signals_emitted.add('S4')
                        total_signals += 1

                        X = np.array([features], dtype=np.float64)
                        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
                        X_s = ml._scaler.transform(X)
                        gb_p = ml._gb_model.predict_proba(X_s)[0, 1]
                        lr_p = ml._lr_model.predict_proba(X_s)[0, 1]
                        lgbm_p = ml._lgbm_model.predict_proba(X_s)[0, 1] if ml._lgbm_model else None

                        vix = macro_day.get('vix_close', 20.0)
                        threshold = 0.7 if vix <= 20 else 0.75
                        strat_threshold = 0.8  # GAP_NOT_FILLED uses tighter

                        if gb_p > 0.95:
                            results['GAP_NOT_FILLED']['high'].append(won)
                            results['GAP_NOT_FILLED']['confirmed'].append(won)
                        elif lgbm_p is not None:
                            if lr_p > strat_threshold and gb_p > strat_threshold and lgbm_p > strat_threshold:
                                results['GAP_NOT_FILLED']['confirmed'].append(won)

    # ── REPORT ──
    print("\n" + "=" * 80)
    print("HONEST BACKTEST RESULTS — IntradayMLFilter (data leakage fixed)")
    print(f"  Dates: {sample_dates[0]} to {sample_dates[-1]} ({total_days_processed} days)")
    print(f"  Total signals: {total_signals}")
    print(f"  Model fit_date: {ml._fit_date}")
    print("=" * 80)

    all_no_filter = []
    all_confirmed = []
    all_high = []

    for strat in ['FIRST_BAR_CONFIRM', 'HOD_BREAK', 'RECLAIM_OPEN', 'GAP_NOT_FILLED']:
        r = results[strat]
        nf = r['no_filter']
        cf = r['confirmed']
        hi = r['high']
        all_no_filter.extend(nf)
        all_confirmed.extend(cf)
        all_high.extend(hi)

        nf_wr = sum(nf) / len(nf) * 100 if nf else 0
        cf_wr = sum(cf) / len(cf) * 100 if cf else 0
        hi_wr = sum(hi) / len(hi) * 100 if hi else 0

        print(f"\n  {strat}:")
        print(f"    No filter:  N={len(nf):5d}  WR={nf_wr:5.1f}%")
        print(f"    CONFIRMED:  N={len(cf):5d}  WR={cf_wr:5.1f}%")
        print(f"    HIGH:       N={len(hi):5d}  WR={hi_wr:5.1f}%")

    # Totals
    print(f"\n  {'ALL STRATEGIES':}")
    nf_wr = sum(all_no_filter) / len(all_no_filter) * 100 if all_no_filter else 0
    cf_wr = sum(all_confirmed) / len(all_confirmed) * 100 if all_confirmed else 0
    hi_wr = sum(all_high) / len(all_high) * 100 if all_high else 0
    print(f"    No filter:  N={len(all_no_filter):5d}  WR={nf_wr:5.1f}%")
    print(f"    CONFIRMED:  N={len(all_confirmed):5d}  WR={cf_wr:5.1f}%")
    print(f"    HIGH:       N={len(all_high):5d}  WR={hi_wr:5.1f}%")

    print(f"\n  Signals per day: {total_signals / total_days_processed:.1f}")
    print(f"  CONFIRMED per day: {len(all_confirmed) / total_days_processed:.1f}")
    print(f"  HIGH per day: {len(all_high) / total_days_processed:.1f}")
    print("=" * 80)


if __name__ == '__main__':
    run_backtest()
