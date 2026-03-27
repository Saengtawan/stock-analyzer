#!/usr/bin/env python3
"""
SL Width Backtest — DIP Bounce signals (QUEUE_FULL)
=====================================================
Uses signal_outcomes.outcome_max_dd_5d to simulate different SL% thresholds.

Method:
  - If outcome_max_dd_5d <= -SL_PCT: SL hit → exit at -SL_PCT
  - Otherwise: hold 5 days → exit at outcome_5d
  - Note: max_dd is close-price-based, not intraday low.
    Real SL hits would be slightly more frequent (conservative estimate).

Signals: QUEUE_FULL DIP signals from signal_outcomes (de-duped by symbol+date).
"""

import sqlite3
from collections import defaultdict

DB = 'data/trade_history.db'
SL_WIDTHS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
CAPITAL = 1250.0  # per slot (v7.0 per-slot sizing)


def load_signals():
    conn = None  # via get_session()
    conn.row_factory = dict
    # De-dup by (symbol, scan_date) — take first row per pair
    rows = conn.execute("""
        SELECT symbol, scan_date, scan_price,
               outcome_1d, outcome_2d, outcome_3d, outcome_4d, outcome_5d,
               outcome_max_dd_5d, outcome_max_gain_5d,
               entry_rsi, volume_ratio, atr_pct, momentum_5d
        FROM signal_outcomes
        WHERE action_taken = 'QUEUE_FULL'
          AND outcome_5d IS NOT NULL
          AND outcome_max_dd_5d IS NOT NULL
        GROUP BY symbol, scan_date
        ORDER BY scan_date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def simulate(signals, sl_pct):
    results = []
    sl_hits = 0
    holds = 0

    for s in signals:
        max_dd = s['outcome_max_dd_5d']  # negative number, e.g. -5.2
        out5d = s['outcome_5d']

        if max_dd <= -sl_pct:
            # SL triggered — exit at -sl_pct
            pnl_pct = -sl_pct
            sl_hits += 1
        else:
            # Hold 5 days
            pnl_pct = out5d
            holds += 1

        results.append({
            'symbol': s['symbol'],
            'date': s['scan_date'],
            'pnl_pct': pnl_pct,
            'sl_hit': max_dd <= -sl_pct,
            'rsi': s['entry_rsi'],
            'vol': s['volume_ratio'],
            'mom5d': s['momentum_5d'],
        })

    return results, sl_hits, holds


def metrics(results):
    n = len(results)
    if n == 0:
        return {}
    wins = [r for r in results if r['pnl_pct'] > 0]
    losses = [r for r in results if r['pnl_pct'] <= 0]
    pnls = [r['pnl_pct'] for r in results]
    total_pnl_usd = sum(r['pnl_pct'] / 100 * CAPITAL for r in results)
    avg_win = sum(r['pnl_pct'] for r in wins) / len(wins) if wins else 0
    avg_loss = sum(r['pnl_pct'] for r in losses) / len(losses) if losses else 0

    return {
        'n': n,
        'wr': len(wins) / n * 100,
        'avg_pnl': sum(pnls) / n,
        'total_pnl_pct': sum(pnls),
        'total_pnl_usd': total_pnl_usd,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': (len(wins)/n * avg_win) + (len(losses)/n * avg_loss),
    }


def main():
    signals = load_signals()
    print(f"Signals loaded: {len(signals)} unique (symbol, date) QUEUE_FULL DIP signals")
    print(f"Date range: {signals[0]['scan_date']} → {signals[-1]['scan_date']}")
    print(f"Capital per trade: ${CAPITAL:.0f} (DIP per-slot)\n")

    # Baseline: always hold 5 days (no SL)
    no_sl_pnls = [s['outcome_5d'] for s in signals]
    no_sl_wins = len([p for p in no_sl_pnls if p > 0])
    no_sl_avg = sum(no_sl_pnls) / len(no_sl_pnls)
    no_sl_total_usd = sum(p / 100 * CAPITAL for p in no_sl_pnls)
    print(f"{'SL%':>6}  {'WR':>6}  {'Avg P&L':>8}  {'Expectancy':>11}  {'Total $':>10}  {'SL hits':>8}  {'Avg win':>8}  {'Avg loss':>9}")
    print(f"{'------':>6}  {'------':>6}  {'--------':>8}  {'-----------':>11}  {'----------':>10}  {'--------':>8}  {'--------':>8}  {'---------':>9}")
    print(f"{'None':>6}  {no_sl_wins/len(signals)*100:>5.1f}%  {no_sl_avg:>+7.2f}%  {'N/A':>11}  ${no_sl_total_usd:>9.0f}  {'0':>8}  {'N/A':>8}  {'N/A':>9}")

    best_expectancy = -999
    best_sl = None
    rows_out = []

    for sl_pct in SL_WIDTHS:
        results, sl_hits, holds = simulate(signals, sl_pct)
        m = metrics(results)
        rows_out.append((sl_pct, m, sl_hits))

        marker = ''
        if m['expectancy'] > best_expectancy:
            best_expectancy = m['expectancy']
            best_sl = sl_pct
            marker = ' ◄'

        print(
            f"{sl_pct:>5.1f}%  {m['wr']:>5.1f}%  {m['avg_pnl']:>+7.2f}%  "
            f"{m['expectancy']:>+10.2f}%  ${m['total_pnl_usd']:>9.0f}  "
            f"{sl_hits:>8}  {m['avg_win']:>+7.2f}%  {m['avg_loss']:>+8.2f}%{marker}"
        )

    print(f"\nBest SL by expectancy: {best_sl}%")

    # Weekly breakdown for best SL
    print(f"\n--- Weekly breakdown at SL={best_sl}% ---")
    results_best, _, _ = simulate(signals, best_sl)
    by_week = defaultdict(list)
    for r in results_best:
        wk = r['date'][:8]  # YYYY-MM-D prefix for grouping
        # get Monday of week
        from datetime import datetime, timedelta
        d = datetime.strptime(r['date'], '%Y-%m-%d')
        monday = (d - timedelta(days=d.weekday())).strftime('%Y-%m-%d')
        by_week[monday].append(r['pnl_pct'])

    print(f"{'Week':>12}  {'n':>4}  {'WR':>6}  {'Avg':>8}  {'Total$':>8}")
    for wk in sorted(by_week):
        pnls = by_week[wk]
        wins = len([p for p in pnls if p > 0])
        avg = sum(pnls)/len(pnls)
        total = sum(p/100*CAPITAL for p in pnls)
        print(f"{wk:>12}  {len(pnls):>4}  {wins/len(pnls)*100:>5.1f}%  {avg:>+7.2f}%  ${total:>7.0f}")

    # RSI analysis at best SL
    print(f"\n--- RSI buckets at SL={best_sl}% (signals with RSI data) ---")
    results_best, _, _ = simulate(signals, best_sl)
    sig_map = {(s['symbol'], s['scan_date']): s for s in signals}

    buckets = defaultdict(list)
    for r in results_best:
        rsi = r['rsi']
        if rsi is None:
            continue
        if rsi < 40:
            b = '<40'
        elif rsi < 45:
            b = '40-45'
        elif rsi < 50:
            b = '45-50'
        elif rsi < 55:
            b = '50-55'
        elif rsi < 60:
            b = '55-60'
        else:
            b = '≥60'
        buckets[b].append(r['pnl_pct'])

    print(f"{'RSI':>7}  {'n':>4}  {'WR':>6}  {'Avg':>8}  {'Total$':>8}")
    for b in ['<40', '40-45', '45-50', '50-55', '55-60', '≥60']:
        if b not in buckets:
            continue
        pnls = buckets[b]
        wins = len([p for p in pnls if p > 0])
        avg = sum(pnls)/len(pnls)
        total = sum(p/100*CAPITAL for p in pnls)
        print(f"{b:>7}  {len(pnls):>4}  {wins/len(pnls)*100:>5.1f}%  {avg:>+7.2f}%  ${total:>7.0f}")


if __name__ == '__main__':
    main()
