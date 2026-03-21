#!/usr/bin/env python3
"""
Replay Discovery v4.4b with Gap Filter — measures impact of pre-market validation.

Methodology:
1. Load combined dataset (backfill + live signal_outcomes + macro)
2. Walk-forward kernel scoring (v4.4b, expanding window)
3. Download next-day open prices for selected picks
4. Compute gap_pct = (open_D+1 / scan_price - 1) * 100
5. Compare: baseline v4.4b vs v4.4b + gap >= 0% filter

Outputs: WR, TP hit rate, SL hit rate, total PnL, per-regime, expectancy.
"""
import datetime as _dt
import sqlite3
import sys
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# === v4.4b config ===
MACRO_BW = 0.6
STOCK_BW = 1.0
BULL_ER = 0.5
STRESS_ER = -0.5
MIN_TRAIN_DAYS = 20
TP_PCT = 3.0
TP2_PCT = 6.0

DEFENSIVE_SECTORS = frozenset({
    'Utilities', 'Healthcare', 'Basic Materials', 'Real Estate', 'Energy',
})
CRISIS_DEFENSIVE = frozenset({
    'Utilities', 'Real Estate', 'Energy',
})

MACRO_FEATURES = ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                  'new_52w_highs', 'yield_10y', 'spy_close']
STOCK_FEATURES = ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                  'new_52w_highs', 'yield_10y', 'spy_close',
                  'atr_pct', 'momentum_5d', 'volume_ratio', 'entry_rsi']


class GaussianKernel:
    def __init__(self, bandwidth, features):
        self.bw = bandwidth
        self.features = features
        self.X = np.array([])
        self.y = np.array([])
        self.mu = np.zeros(len(features))
        self.sigma = np.ones(len(features))

    def fit(self, data):
        rows, rets = [], []
        for r in data:
            vals = [r.get(f) for f in self.features]
            if any(v is None for v in vals):
                continue
            rows.append(vals)
            rets.append(r['outcome_5d'])
        if len(rows) < 10:
            self.X = np.array([])
            return
        self.X = np.array(rows, dtype=float)
        self.y = np.array(rets, dtype=float)
        self.mu = self.X.mean(axis=0)
        self.sigma = self.X.std(axis=0)
        self.sigma[self.sigma == 0] = 1.0
        self.X = (self.X - self.mu) / self.sigma

    def estimate(self, row):
        if len(self.X) == 0:
            return 0.0, 0.0
        vals = []
        for i, f in enumerate(self.features):
            v = row.get(f)
            if v is None:
                v = self.mu[i]
            vals.append(v)
        x = (np.array(vals, dtype=float) - self.mu) / self.sigma
        dists = np.sqrt(np.sum((self.X - x) ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 0.0
        er = float(np.sum(weights * self.y) / total_w)
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))
        return er, n_eff


def load_data():
    """Load combined dataset with macro features."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    live_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector, s.scan_price,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_1d, s.outcome_2d, s.outcome_3d, s.outcome_5d,
               s.outcome_max_gain_5d, s.outcome_max_dd_5d,
               m.crude_close, m.yield_10y, m.spy_close,
               b.pct_above_20d_ma, b.new_52w_lows, b.new_52w_highs
        FROM signal_outcomes s
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        LEFT JOIN market_breadth b
            ON b.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        WHERE s.outcome_5d IS NOT NULL AND s.atr_pct IS NOT NULL
          AND s.signal_source = 'dip_bounce'
    """).fetchall()

    backfill_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector, s.scan_price,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_1d, s.outcome_2d, s.outcome_3d, s.outcome_5d,
               s.outcome_max_gain_5d, s.outcome_max_dd_5d,
               m.crude_close, m.yield_10y, m.spy_close,
               b.pct_above_20d_ma, b.new_52w_lows, b.new_52w_highs
        FROM backfill_signal_outcomes s
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        LEFT JOIN market_breadth b
            ON b.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        WHERE s.outcome_5d IS NOT NULL
    """).fetchall()

    crude_series = conn.execute("""
        SELECT date, crude_close FROM macro_snapshots
        WHERE crude_close IS NOT NULL ORDER BY date
    """).fetchall()
    conn.close()

    crude_by_date = {r['date']: r['crude_close'] for r in crude_series}
    crude_dates = sorted(crude_by_date.keys())
    crude_chg_by_date = {}
    for i, d in enumerate(crude_dates):
        if i >= 5:
            c5 = crude_by_date[crude_dates[i - 5]]
            if c5 and c5 > 0:
                crude_chg_by_date[d] = (crude_by_date[d] / c5 - 1) * 100

    combined = []
    for r in backfill_rows:
        d = dict(r); d['source'] = 'backfill'; combined.append(d)
    for r in live_rows:
        d = dict(r); d['source'] = 'live'; combined.append(d)

    seen = {}
    for row in combined:
        key = (row['scan_date'], row['symbol'])
        if key in seen:
            if row['source'] == 'live': seen[key] = row
        else:
            seen[key] = row
    combined = sorted(seen.values(), key=lambda r: r['scan_date'])

    for row in combined:
        sd = row['scan_date']
        d_obj = _dt.date.fromisoformat(sd)
        wd = d_obj.weekday()
        if wd == 5: macro_d = (d_obj - _dt.timedelta(days=1)).isoformat()
        elif wd == 6: macro_d = (d_obj - _dt.timedelta(days=2)).isoformat()
        else: macro_d = sd
        row['crude_change_5d'] = crude_chg_by_date.get(macro_d)

    print(f"Dataset: {len(combined)} rows, {len(set(r['scan_date'] for r in combined))} dates")
    return combined


def download_open_prices(picks):
    """Download next-day open prices for all picks via yfinance."""
    import yfinance as yf

    # Group by symbol
    by_symbol = defaultdict(list)
    for p in picks:
        by_symbol[p['symbol']].append(p)

    symbols = list(by_symbol.keys())
    print(f"Downloading open prices for {len(symbols)} symbols...")

    # Need full date range
    all_dates = [_dt.date.fromisoformat(p['date']) for p in picks]
    min_date = min(all_dates) - _dt.timedelta(days=5)
    max_date = max(all_dates) + _dt.timedelta(days=10)
    start_str = min_date.isoformat()
    end_str = max_date.isoformat()

    # Batch download
    batch_size = 50
    open_cache = {}  # (symbol, date_str) -> open_price

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_str = ' '.join(batch)
        try:
            data = yf.download(batch_str, start=start_str, end=end_str,
                               interval='1d', auto_adjust=True,
                               progress=False, threads=False)
            if data.empty:
                continue

            for sym in batch:
                try:
                    if len(batch) == 1:
                        opens = data['Open']
                    else:
                        if sym not in data.columns.get_level_values(1):
                            continue
                        opens = data['Open'][sym]

                    for idx, val in opens.dropna().items():
                        date_str = idx.strftime('%Y-%m-%d')
                        open_cache[(sym, date_str)] = float(val)
                except Exception:
                    continue
        except Exception as e:
            print(f"  batch error: {e}")
            continue

        if (i // batch_size + 1) % 5 == 0:
            print(f"  batch {i // batch_size + 1}/{(len(symbols) + batch_size - 1) // batch_size}")

    # Compute gap_pct for each pick
    filled = 0
    for p in picks:
        scan_date = _dt.date.fromisoformat(p['date'])
        sym = p['symbol']

        # Find next trading day's open
        for offset in range(1, 5):
            next_day = scan_date + _dt.timedelta(days=offset)
            next_str = next_day.isoformat()
            if (sym, next_str) in open_cache:
                open_price = open_cache[(sym, next_str)]
                scan_price = p.get('scan_price', 0)
                if scan_price and scan_price > 0:
                    p['gap_pct'] = (open_price / scan_price - 1) * 100
                    p['open_price'] = open_price
                    filled += 1
                break

    print(f"Gap data: {filled}/{len(picks)} picks ({filled/len(picks)*100:.0f}%)")
    return picks


def run_walkforward(data):
    """Run v4.4b walk-forward and collect all picks with detailed outcomes."""
    dates = sorted(set(r['scan_date'] for r in data))
    all_picks = []
    regime_days = defaultdict(int)
    skipped = 0

    for test_date in dates:
        train = [r for r in data if r['scan_date'] < test_date]
        test = [r for r in data if r['scan_date'] == test_date]
        if not test:
            continue
        if len(set(r['scan_date'] for r in train)) < MIN_TRAIN_DAYS:
            skipped += 1
            continue

        # Macro kernel → regime
        macro_k = GaussianKernel(MACRO_BW, MACRO_FEATURES)
        macro_k.fit(train)
        macro_er, macro_neff = macro_k.estimate(test[0])
        if macro_neff < 3.0:
            skipped += 1
            continue

        if macro_er > BULL_ER:
            regime, max_picks, sl_pct = 'BULL', 5, 3.0
        elif macro_er > STRESS_ER:
            regime, max_picks, sl_pct = 'STRESS', 3, 2.0
        else:
            regime, max_picks, sl_pct = 'CRISIS', 2, 2.0
        regime_days[regime] += 1

        # Stock kernel → rank
        stock_k = GaussianKernel(STOCK_BW, STOCK_FEATURES)
        stock_k.fit(train)

        scored = []
        for row in test:
            stock_er, stock_neff = stock_k.estimate(row)
            if stock_neff < 3.0:
                stock_er = 0.0

            if regime == 'STRESS':
                atr = row.get('atr_pct') or 99
                mom5 = row.get('momentum_5d') or 0
                sector = row.get('sector') or ''
                bonus = 0
                if atr < 2.5: bonus += 1
                if mom5 < 0: bonus += 1
                if (row.get('volume_ratio') or 0) > 1.2: bonus += 1
                if sector in DEFENSIVE_SECTORS: bonus += 1
                if bonus < 2: continue
                stock_er += bonus * 0.5
            elif regime == 'CRISIS':
                mom5 = row.get('momentum_5d') or 0
                sector = row.get('sector') or ''
                if mom5 >= 0: continue
                bonus = 0
                if (row.get('atr_pct') or 99) < 2.5: bonus += 1
                if mom5 < -2: bonus += 1
                if (row.get('volume_ratio') or 0) > 1.5: bonus += 1
                if sector in CRISIS_DEFENSIVE: bonus += 1
                if bonus < 3: continue
                stock_er += bonus * 0.5

            if stock_er < 0: continue
            scored.append((stock_er, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        for stock_er, row in scored[:max_picks]:
            mg = row.get('outcome_max_gain_5d')
            md = row.get('outcome_max_dd_5d')

            # Capped return with SL/TP
            if mg is not None and md is not None:
                if md <= -sl_pct:
                    capped = -sl_pct
                elif mg >= TP_PCT:
                    capped = TP_PCT
                else:
                    capped = row['outcome_5d']
            else:
                capped = row['outcome_5d']

            # TP/SL hit classification
            hit_sl = md is not None and md <= -sl_pct
            hit_tp1 = mg is not None and mg >= TP_PCT
            hit_tp2 = mg is not None and mg >= TP2_PCT

            all_picks.append({
                'date': test_date,
                'symbol': row['symbol'],
                'regime': regime,
                'stock_er': stock_er,
                'scan_price': row.get('scan_price'),
                'capped_return': capped,
                'raw_return_5d': row['outcome_5d'],
                'outcome_1d': row.get('outcome_1d'),
                'max_gain_5d': mg,
                'max_dd_5d': md,
                'sl_pct': sl_pct,
                'hit_sl': hit_sl,
                'hit_tp1': hit_tp1,
                'hit_tp2': hit_tp2,
                'sector': row.get('sector'),
                'atr_pct': row.get('atr_pct'),
                'gap_pct': None,  # filled later
            })

    print(f"Walk-forward: {len(all_picks)} picks, {len(set(p['date'] for p in all_picks))} days, skipped {skipped}")
    print(f"Regime days: {dict(regime_days)}")
    return all_picks


def compute_metrics(picks, label):
    """Compute comprehensive metrics for a set of picks."""
    if not picks:
        return None

    n = len(picks)
    capped = [p['capped_return'] for p in picks]
    raw = [p['raw_return_5d'] for p in picks]
    total_pnl = sum(capped)
    wins = sum(1 for c in capped if c > 0)
    wr = wins / n * 100
    avg_capped = np.mean(capped)
    avg_raw = np.mean(raw)

    tp1_hits = sum(1 for p in picks if p['hit_tp1'])
    sl_hits = sum(1 for p in picks if p['hit_sl'])
    tp2_hits = sum(1 for p in picks if p['hit_tp2'])
    neither = n - tp1_hits - sl_hits  # exited at D5 without TP/SL

    # Expectancy = avg win * WR - avg loss * (1-WR)
    win_returns = [c for c in capped if c > 0]
    loss_returns = [c for c in capped if c <= 0]
    avg_win = np.mean(win_returns) if win_returns else 0
    avg_loss = np.mean(loss_returns) if loss_returns else 0
    expectancy = avg_win * (wins / n) + avg_loss * ((n - wins) / n) if n > 0 else 0

    dates_set = sorted(set(p['date'] for p in picks))

    # Per-regime breakdown
    regime_data = {}
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        rp = [p for p in picks if p['regime'] == regime]
        if rp:
            rc = [p['capped_return'] for p in rp]
            rw = sum(1 for c in rc if c > 0)
            r_tp1 = sum(1 for p in rp if p['hit_tp1'])
            r_sl = sum(1 for p in rp if p['hit_sl'])
            regime_data[regime] = {
                'n': len(rp), 'wr': rw / len(rp) * 100,
                'pnl': sum(rc), 'avg': np.mean(rc),
                'tp1_rate': r_tp1 / len(rp) * 100,
                'sl_rate': r_sl / len(rp) * 100,
            }
        else:
            regime_data[regime] = {'n': 0, 'wr': 0, 'pnl': 0, 'avg': 0, 'tp1_rate': 0, 'sl_rate': 0}

    return {
        'label': label, 'n': n, 'n_days': len(dates_set),
        'total_pnl': total_pnl, 'avg_capped': avg_capped, 'avg_raw': avg_raw,
        'win_rate': wr,
        'tp1_rate': tp1_hits / n * 100, 'tp1_hits': tp1_hits,
        'tp2_rate': tp2_hits / n * 100, 'tp2_hits': tp2_hits,
        'sl_rate': sl_hits / n * 100, 'sl_hits': sl_hits,
        'neither_rate': neither / n * 100,
        'avg_win': avg_win, 'avg_loss': avg_loss,
        'expectancy': expectancy,
        'regimes': regime_data,
    }


def print_comparison(baseline, filtered, gap_stats):
    """Print side-by-side comparison."""
    b, f = baseline, filtered

    print(f"\n{'=' * 78}")
    print(f"  DISCOVERY v4.4b REPLAY — Gap Filter Impact Analysis")
    print(f"  Dataset: {b['n_days']} trading days, {gap_stats['total']} picks with gap data")
    print(f"{'=' * 78}")

    print(f"\n  {'Metric':<30} {'Baseline':>18} {'Gap>=0%':>18} {'Delta':>12}")
    print(f"  {'─' * 72}")

    rows = [
        ('Picks', 'n', 'd', ''),
        ('Trading Days', 'n_days', 'd', ''),
        ('Win Rate (%)', 'win_rate', '.1f', '%'),
        ('Avg Capped Return (%)', 'avg_capped', '.3f', '%'),
        ('Avg Raw Return 5d (%)', 'avg_raw', '.3f', '%'),
        ('Total PnL (%)', 'total_pnl', '.1f', '%'),
        ('TP1 Hit Rate (%)', 'tp1_rate', '.1f', '%'),
        ('TP2 Hit Rate (%)', 'tp2_rate', '.1f', '%'),
        ('SL Hit Rate (%)', 'sl_rate', '.1f', '%'),
        ('Exit@D5 Rate (%)', 'neither_rate', '.1f', '%'),
        ('Avg Win (%)', 'avg_win', '.2f', '%'),
        ('Avg Loss (%)', 'avg_loss', '.2f', '%'),
        ('Expectancy (%)', 'expectancy', '.3f', '%'),
    ]

    for label, key, fmt, suffix in rows:
        bv = b[key]
        fv = f[key] if f else 0
        delta = fv - bv if f else 0
        delta_str = f"{delta:+.1f}" if abs(delta) > 0.05 else "—"
        print(f"  {label:<30} {format(bv, fmt) + suffix:>18} {format(fv, fmt) + suffix if f else '—':>18} {delta_str:>12}")

    # Per-regime
    print(f"\n  {'─' * 72}")
    print(f"  {'PER REGIME':<30} {'Baseline':>18} {'Gap>=0%':>18} {'Delta':>12}")
    print(f"  {'─' * 72}")

    for regime in ['BULL', 'STRESS', 'CRISIS']:
        br = b['regimes'][regime]
        fr = f['regimes'][regime] if f else {'n': 0, 'wr': 0, 'pnl': 0, 'tp1_rate': 0, 'sl_rate': 0}
        if br['n'] > 0:
            b_str = f"n={br['n']} WR={br['wr']:.0f}% PnL={br['pnl']:+.1f}%"
            if f and fr['n'] > 0:
                f_str = f"n={fr['n']} WR={fr['wr']:.0f}% PnL={fr['pnl']:+.1f}%"
                wr_delta = fr['wr'] - br['wr']
                delta_str = f"WR{wr_delta:+.0f}pp"
            else:
                f_str = "—"
                delta_str = "—"
            print(f"  {regime:<30} {b_str:>18} {f_str:>18} {delta_str:>12}")

    # Gap distribution
    print(f"\n  {'─' * 72}")
    print(f"  GAP DISTRIBUTION")
    print(f"  {'─' * 72}")
    print(f"  Gap >= 0%: {gap_stats['positive']} picks ({gap_stats['positive']/gap_stats['total']*100:.0f}%)")
    print(f"  Gap < 0%:  {gap_stats['negative']} picks ({gap_stats['negative']/gap_stats['total']*100:.0f}%)")
    print(f"  Missing:   {gap_stats['missing']} picks")
    print(f"  Avg gap (all):   {gap_stats['avg_gap']:+.2f}%")
    print(f"  Avg gap (>=0):   {gap_stats['avg_pos_gap']:+.2f}%")
    print(f"  Avg gap (<0):    {gap_stats['avg_neg_gap']:+.2f}%")

    # Gap bucket analysis
    print(f"\n  {'─' * 72}")
    print(f"  GAP BUCKET ANALYSIS")
    print(f"  {'─' * 72}")
    print(f"  {'Gap Range':<18} {'N':>5} {'WR':>7} {'Avg5d':>8} {'TP1%':>7} {'SL%':>7} {'PnL':>8}")
    print(f"  {'─' * 62}")

    buckets = [
        ('< -2%', lambda g: g < -2),
        ('-2% to -1%', lambda g: -2 <= g < -1),
        ('-1% to 0%', lambda g: -1 <= g < 0),
        ('0% to +1%', lambda g: 0 <= g < 1),
        ('+1% to +2%', lambda g: 1 <= g < 2),
        ('>= +2%', lambda g: g >= 2),
    ]
    for bkt_label, bkt_fn in buckets:
        bp = [p for p in gap_stats['picks_with_gap'] if bkt_fn(p['gap_pct'])]
        if bp:
            bc = [p['capped_return'] for p in bp]
            bw = sum(1 for c in bc if c > 0)
            bt1 = sum(1 for p in bp if p['hit_tp1'])
            bs = sum(1 for p in bp if p['hit_sl'])
            print(f"  {bkt_label:<18} {len(bp):>5} {bw/len(bp)*100:>6.1f}% {np.mean(bc):>+7.2f}% {bt1/len(bp)*100:>6.1f}% {bs/len(bp)*100:>6.1f}% {sum(bc):>+7.1f}%")

    print(f"\n{'=' * 78}")


def main():
    data = load_data()

    # Step 1: Walk-forward scoring
    print("\n--- Step 1: Walk-forward v4.4b scoring ---")
    picks = run_walkforward(data)

    # Step 2: Download open prices and compute gap
    print("\n--- Step 2: Downloading open prices for gap computation ---")
    picks = download_open_prices(picks)

    # Step 3: Compute metrics
    print("\n--- Step 3: Computing metrics ---")

    picks_with_gap = [p for p in picks if p.get('gap_pct') is not None]
    gap_pos = [p for p in picks_with_gap if p['gap_pct'] >= 0]
    gap_neg = [p for p in picks_with_gap if p['gap_pct'] < 0]

    gap_stats = {
        'total': len(picks_with_gap),
        'positive': len(gap_pos),
        'negative': len(gap_neg),
        'missing': len(picks) - len(picks_with_gap),
        'avg_gap': np.mean([p['gap_pct'] for p in picks_with_gap]) if picks_with_gap else 0,
        'avg_pos_gap': np.mean([p['gap_pct'] for p in gap_pos]) if gap_pos else 0,
        'avg_neg_gap': np.mean([p['gap_pct'] for p in gap_neg]) if gap_neg else 0,
        'picks_with_gap': picks_with_gap,
    }

    baseline = compute_metrics(picks_with_gap, 'Baseline v4.4b')
    filtered = compute_metrics(gap_pos, 'v4.4b + Gap>=0%') if gap_pos else None

    print_comparison(baseline, filtered, gap_stats)


if __name__ == '__main__':
    main()
