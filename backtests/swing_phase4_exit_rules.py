"""
Phase 4 — Exit Rule Optimization.

For the top 3-5 (label, threshold) survivors from Phase 3, simulate
multiple exit rule combinations and pick the best.

Exit rule axes:
  - TP target: 1.5%, 2%, 3%, 5%, 7%, 10%
  - SL: -2%, -3%, -5%, -7%, none
  - Time stop: 3d, 5d, 7d, 14d, 30d
  - (advanced) Trail stop: 1%, 2%, 3% — needs more forward data

Output: backtests/results_swing/phase4_exit_grid.csv
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sqlite3

CACHE = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/cache_swing')
RESULTS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/results_swing')
MODELS = Path('/home/saengtawan/work/project/cc/stock-analyzer/backtests/models_swing')
DB = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db')

TP_VARIANTS = [1.5, 2.0, 3.0, 5.0, 7.0, 10.0]
SL_VARIANTS = [-2.0, -3.0, -5.0, -7.0, None]
TIME_STOPS = [3, 5, 7, 14, 30]


def load_full_history(symbols):
    """Load daily history for trade simulation."""
    con = sqlite3.connect(str(DB))
    syms_str = ",".join([f"'{s}'" for s in symbols])
    df = pd.read_sql(
        f"SELECT symbol, date, open, high, low, close FROM stock_daily_ohlc "
        f"WHERE symbol IN ({syms_str}) AND date >= '2019-01-01' "
        "ORDER BY symbol, date",
        con
    )
    con.close()
    df['date'] = pd.to_datetime(df['date'])
    return df


def simulate_trade(entry_close, future_bars, tp_pct, sl_pct, time_stop):
    """Walk forward bar-by-bar, apply exit rules.
    Returns: (exit_pnl_pct, exit_day, exit_reason)
    """
    if future_bars is None or len(future_bars) == 0:
        return np.nan, 0, 'no_data'

    tp_price = entry_close * (1 + tp_pct / 100)
    sl_price = entry_close * (1 + sl_pct / 100) if sl_pct is not None else None

    for day_i in range(min(time_stop, len(future_bars))):
        bar = future_bars.iloc[day_i]
        # Check SL first (conservative)
        if sl_price is not None and bar['low'] <= sl_price:
            return sl_pct, day_i + 1, 'sl'
        # Check TP
        if bar['high'] >= tp_price:
            return tp_pct, day_i + 1, 'tp'

    # Time stop
    if len(future_bars) >= time_stop:
        exit_price = future_bars.iloc[time_stop - 1]['close']
    else:
        exit_price = future_bars.iloc[-1]['close']
    pnl = (exit_price - entry_close) / entry_close * 100
    return pnl, len(future_bars), 'time'


def evaluate_exit_combo(picks_df, hist_df, tp, sl, time_stop):
    """For each pick, simulate trade with these exit rules. Return aggregated metrics."""
    results = []
    hist_indexed = hist_df.set_index(['symbol', 'date']).sort_index()

    pnls = []
    days = []
    reasons = []
    for _, row in picks_df.iterrows():
        sym = row['symbol']
        date = pd.to_datetime(row['date'])

        # Get future bars (next 30 days)
        try:
            sym_hist = hist_df[hist_df['symbol'] == sym].sort_values('date').reset_index(drop=True)
            entry_idx = sym_hist[sym_hist['date'] == date].index
            if len(entry_idx) == 0:
                continue
            entry_idx = entry_idx[0]
            entry_close = sym_hist.iloc[entry_idx]['close']
            future = sym_hist.iloc[entry_idx + 1:entry_idx + 1 + time_stop + 1]
            if len(future) == 0:
                continue
            pnl, day, reason = simulate_trade(entry_close, future, tp, sl, time_stop)
            if not pd.isna(pnl):
                pnls.append(pnl)
                days.append(day)
                reasons.append(reason)
        except Exception:
            continue

    if not pnls:
        return None

    pnls = np.array(pnls)
    n = len(pnls)
    wins = (pnls > 0).sum()
    wr = wins / n
    avg_pnl = pnls.mean()
    avg_win = pnls[pnls > 0].mean() if wins > 0 else 0
    avg_loss = pnls[pnls <= 0].mean() if (n - wins) > 0 else 0
    std = pnls.std() if n > 1 else 1
    sharpe = avg_pnl / std * np.sqrt(252 / max(time_stop, 1)) if std > 0 else 0
    avg_days = np.mean(days)

    reason_dist = pd.Series(reasons).value_counts(normalize=True).to_dict()

    return {
        'tp_pct': tp,
        'sl_pct': sl if sl is not None else 'none',
        'time_stop_d': time_stop,
        'n': n,
        'wr': round(wr, 3),
        'avg_pnl': round(avg_pnl, 3),
        'avg_win': round(avg_win, 3),
        'avg_loss': round(avg_loss, 3),
        'std': round(std, 3),
        'sharpe_est': round(sharpe, 2),
        'avg_days': round(avg_days, 1),
        'pct_tp': round(reason_dist.get('tp', 0), 3),
        'pct_sl': round(reason_dist.get('sl', 0), 3),
        'pct_time': round(reason_dist.get('time', 0), 3),
    }


def main():
    print("== Phase 4: Exit Rule Optimization ==")
    start = datetime.now()

    # Load Phase 3 survivors
    survivors_csv = RESULTS / 'phase3_survivors.csv'
    if not survivors_csv.exists():
        print(f"❌ No survivors file at {survivors_csv}. Run Phase 3 first.")
        return

    survivors = pd.read_csv(survivors_csv)
    if len(survivors) == 0:
        # Fall back to top by sharpe
        print("No strict survivors — using top 5 by Sharpe from full results")
        survivors = pd.read_csv(RESULTS / 'phase3_grid_results.csv')
        survivors = survivors.sort_values('sharpe_est', ascending=False).head(5)

    print(f"Optimizing {len(survivors)} candidate (label, threshold) pairs")

    all_results = []
    for _, surv in survivors.iterrows():
        label = surv['label']
        thr = surv['threshold']
        print(f"\n--- {label} @ thr={thr} ---")

        preds_path = MODELS / f'preds_{label}.pkl'
        if not preds_path.exists():
            print(f"  ⚠️ No preds file at {preds_path}")
            continue

        preds = pd.read_pickle(preds_path)
        picks = preds[preds['prob'] >= thr]
        if len(picks) < 30:
            print(f"  Too few picks ({len(picks)})")
            continue

        print(f"  Picks: {len(picks)}")
        # Load history for relevant symbols
        syms = picks['symbol'].unique().tolist()
        print(f"  Loading history for {len(syms)} symbols...")
        hist = load_full_history(syms)
        print(f"  History: {len(hist):,} rows")

        # Grid search over TP × SL × time_stop
        combo_results = []
        for tp in TP_VARIANTS:
            for sl in SL_VARIANTS:
                for ts in TIME_STOPS:
                    if sl is not None and abs(sl) >= tp:
                        continue  # SL must be smaller than TP for sensible trade
                    metrics = evaluate_exit_combo(picks, hist, tp, sl, ts)
                    if metrics:
                        metrics['label'] = label
                        metrics['threshold'] = thr
                        combo_results.append(metrics)

        if combo_results:
            combo_df = pd.DataFrame(combo_results)
            combo_df = combo_df.sort_values('sharpe_est', ascending=False)
            print(f"\n  Top 10 exit combos for {label} @ {thr}:")
            print(combo_df.head(10).to_string(index=False))
            all_results.append(combo_df)

    if all_results:
        final = pd.concat(all_results, ignore_index=True)
        final.to_csv(RESULTS / 'phase4_exit_grid.csv', index=False)

        print("\n== TOP 20 across all (label, thr, exit) ==")
        top = final.sort_values('sharpe_est', ascending=False).head(20)
        print(top.to_string(index=False))

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n✅ Phase 4 done in {elapsed:.0f}s ({elapsed/60:.1f} min)")


if __name__ == '__main__':
    main()
