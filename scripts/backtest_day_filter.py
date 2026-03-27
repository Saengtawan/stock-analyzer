#!/usr/bin/env python3
"""
Day-of Market Filter Backtest
==============================
Tests SPY day return + sector ETF day return filters on QUEUE_FULL DIP signals.

Hypothesis tested:
  - Buying when SPY is down heavily → worse outcomes
  - Buying when signal's sector is down heavily → worse outcomes
  - Filtering these out improves WR and expectancy

DATASET LIMITATION (run: 2026-03-09)
  - signal_outcomes covers Feb 7 – Feb 26, 2026 ONLY (pre-war period)
  - outcome_5d requires 5 trading days → Mar signals not yet settled
  - SPY ≥-2% filter blocked 0 signals (no day in Feb had SPY ≤-2%)
  - US-Israel/Iran war started Mar 2, 2026 → NOT in this dataset

FINDING (Feb 2026, n=205):
  - Sector/SPY day filter NOT recommended for DIP strategy
  - Blocked signals have HIGHER WR than kept signals (contrarian effect)
  - e.g. Sector ≤-0.5% blocked: WR=65% vs kept: WR=46%
  - Interpretation: DIP on already-down sector day = more oversold = stronger bounce
  - All filter combos made expectancy WORSE vs baseline

RE-RUN INSTRUCTIONS (when Mar 2026+ data available):
  - python3 scripts/backtest_day_filter.py
  - Compare results vs Feb baseline
  - If finding consistent → contrarian effect confirmed (don't add filter)
  - If finding reversed in crash/war period → regime-dependent (add conditional filter)

Data:
  - signal_outcomes: QUEUE_FULL DIP signals (de-duped by symbol+date)
  - yfinance: SPY + 11 sector ETFs daily returns
  - sector_cache: symbol → sector name mapping
"""

import sqlite3
import yfinance as yf
import pandas as pd
from collections import defaultdict
from itertools import product

DB = 'data/trade_history.db'
CAPITAL = 1250.0  # per slot

SECTOR_ETF_MAP = {
    'Technology': 'XLK',
    'Real Estate': 'XLRE',
    'Energy': 'XLE',
    'Financial Services': 'XLF',
    'Healthcare': 'XLV',
    'Consumer Cyclical': 'XLY',
    'Consumer Defensive': 'XLP',
    'Industrials': 'XLI',
    'Utilities': 'XLU',
    'Basic Materials': 'XLB',
    'Communication Services': 'XLC',
}

SPY_THRESHOLDS  = [None, -1.0, -1.5, -2.0]   # None = no filter
SECT_THRESHOLDS = [None, -0.5, -1.0, -1.5]


# ── 1. Load signals ────────────────────────────────────────────────────────────

def load_signals():
    conn = None  # via get_session()
    conn.row_factory = dict
    rows = conn.execute("""
        SELECT symbol, scan_date, scan_price,
               outcome_5d, outcome_max_dd_5d,
               entry_rsi, volume_ratio, atr_pct, momentum_5d
        FROM signal_outcomes
        WHERE action_taken = 'QUEUE_FULL'
          AND signal_source = 'dip_bounce'
          AND outcome_5d IS NOT NULL
          AND outcome_max_dd_5d IS NOT NULL
        GROUP BY symbol, scan_date
        ORDER BY scan_date
    """).fetchall()

    # Load sector_cache
    cache = conn.execute("SELECT symbol, sector FROM sector_cache").fetchall()
    sector_map = {r['symbol']: r['sector'] for r in cache}

    conn.close()

    signals = []
    for r in rows:
        s = dict(r)
        s['sector'] = sector_map.get(r['symbol'])
        s['sector_etf'] = SECTOR_ETF_MAP.get(s['sector'])
        signals.append(s)

    return signals


# ── 2. Fetch daily returns ─────────────────────────────────────────────────────

def fetch_daily_returns(signals):
    dates = sorted(set(s['scan_date'] for s in signals))
    start = dates[0]
    end   = dates[-1]

    tickers = ['SPY'] + list(SECTOR_ETF_MAP.values())
    print(f"Fetching {len(tickers)} tickers: {start} → {end} ...")

    raw = yf.download(tickers, start=start, end=pd.Timestamp(end) + pd.Timedelta(days=3),
                      auto_adjust=True, progress=False)['Close']
    daily_ret = raw.pct_change() * 100  # % return

    # Build dict: {date_str: {ticker: return%}}
    ret_by_date = {}
    for ts, row in daily_ret.iterrows():
        d = ts.strftime('%Y-%m-%d')
        ret_by_date[d] = {ticker: row[ticker] for ticker in tickers}

    return ret_by_date


# ── 3. Simulate with filters ──────────────────────────────────────────────────

def simulate(signals, ret_by_date, spy_thresh, sect_thresh):
    kept   = []
    blocked_spy  = []
    blocked_sect = []

    for s in signals:
        date_ret = ret_by_date.get(s['scan_date'], {})
        spy_ret  = date_ret.get('SPY')

        # SPY filter
        if spy_thresh is not None and spy_ret is not None:
            if spy_ret <= spy_thresh:
                blocked_spy.append(s)
                continue

        # Sector filter
        if sect_thresh is not None and s['sector_etf']:
            sect_ret = date_ret.get(s['sector_etf'])
            if sect_ret is not None and sect_ret <= sect_thresh:
                blocked_sect.append(s)
                continue

        kept.append(s)

    return kept, blocked_spy, blocked_sect


# ── 4. Metrics ────────────────────────────────────────────────────────────────

def metrics(signals):
    if not signals:
        return None
    pnls = [s['outcome_5d'] for s in signals]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_usd = sum(p / 100 * CAPITAL for p in pnls)
    avg_win  = sum(wins)  / len(wins)   if wins   else 0
    avg_loss = sum(losses)/ len(losses) if losses else 0
    wr = len(wins) / len(pnls) * 100
    expectancy = (len(wins)/len(pnls) * avg_win) + (len(losses)/len(pnls) * avg_loss)
    return {
        'n': len(pnls),
        'wr': wr,
        'avg_pnl': sum(pnls)/len(pnls),
        'expectancy': expectancy,
        'total_usd': total_usd,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }


# ── 5. Main ───────────────────────────────────────────────────────────────────

def main():
    signals = load_signals()
    print(f"Signals: {len(signals)} QUEUE_FULL DIP (unique symbol+date)")
    print(f"Date range: {signals[0]['scan_date']} → {signals[-1]['scan_date']}")

    has_sector = sum(1 for s in signals if s['sector_etf'])
    print(f"Sector coverage: {has_sector}/{len(signals)} ({has_sector/len(signals)*100:.0f}%)")

    ret_by_date = fetch_daily_returns(signals)
    print(f"Fetched returns for {len(ret_by_date)} trading days\n")

    # Baseline
    base = metrics(signals)
    print(f"{'SPY':>6}  {'Sect':>6}  {'N kept':>7}  {'Blocked':>7}  {'WR kept':>8}  "
          f"{'WR blk':>7}  {'Exp kept':>9}  {'Total $':>10}  {'$ delta':>9}")
    print('-' * 90)
    print(f"{'None':>6}  {'None':>6}  {base['n']:>7}  {'0':>7}  "
          f"{base['wr']:>7.1f}%  {'N/A':>7}  {base['expectancy']:>+8.2f}%  "
          f"${base['total_usd']:>9.0f}  {'baseline':>9}")

    best_exp = base['expectancy']
    best_combo = None

    results = []
    for spy_t, sect_t in product(SPY_THRESHOLDS, SECT_THRESHOLDS):
        if spy_t is None and sect_t is None:
            continue

        kept, b_spy, b_sect = simulate(signals, ret_by_date, spy_t, sect_t)
        blocked_all = b_spy + b_sect

        m_kept  = metrics(kept)
        m_block = metrics(blocked_all)

        if not m_kept:
            continue

        spy_label  = f"{spy_t:+.1f}%" if spy_t  is not None else "None"
        sect_label = f"{sect_t:+.1f}%" if sect_t is not None else "None"
        delta_usd  = m_kept['total_usd'] - base['total_usd']

        marker = ''
        if m_kept['expectancy'] > best_exp:
            best_exp = m_kept['expectancy']
            best_combo = (spy_t, sect_t)
            marker = ' ◄ BEST'

        blk_wr = f"{m_block['wr']:>6.1f}%" if m_block else "   N/A"
        print(f"{spy_label:>6}  {sect_label:>6}  {m_kept['n']:>7}  {len(blocked_all):>7}  "
              f"{m_kept['wr']:>7.1f}%  "
              f"{blk_wr}  "
              f"{m_kept['expectancy']:>+8.2f}%  "
              f"${m_kept['total_usd']:>9.0f}  "
              f"{delta_usd:>+9.0f}{marker}")

        results.append({'spy': spy_t, 'sect': sect_t, 'm_kept': m_kept,
                        'm_block': m_block, 'n_blocked': len(blocked_all)})

    # Detail on best combo
    if best_combo:
        spy_t, sect_t = best_combo
        kept, b_spy, b_sect = simulate(signals, ret_by_date, spy_t, sect_t)
        print(f"\n{'─'*60}")
        print(f"Best combo: SPY≤{spy_t}%  Sector≤{sect_t}%")
        print(f"  Blocked by SPY: {len(b_spy)}  |  Blocked by sector: {len(b_sect)}")

        # WR by SPY return bucket
        print(f"\n--- SPY day return buckets (all signals, 5d outcome) ---")
        spy_buckets = defaultdict(list)
        for s in signals:
            date_ret = ret_by_date.get(s['scan_date'], {})
            spy_ret = date_ret.get('SPY')
            if spy_ret is None:
                continue
            if spy_ret <= -2.0:   b = '≤-2.0%'
            elif spy_ret <= -1.5: b = '-2.0 to -1.5%'
            elif spy_ret <= -1.0: b = '-1.5 to -1.0%'
            elif spy_ret <= -0.5: b = '-1.0 to -0.5%'
            elif spy_ret <= 0:    b = '-0.5 to 0%'
            elif spy_ret <= 0.5:  b = '0 to +0.5%'
            elif spy_ret <= 1.0:  b = '+0.5 to +1.0%'
            else:                  b = '>+1.0%'
            spy_buckets[b].append(s['outcome_5d'])

        print(f"  {'SPY day':>16}  {'n':>5}  {'WR':>6}  {'Avg 5d':>8}  {'Total $':>9}")
        for b in ['≤-2.0%','−2.0 to -1.5%','−1.5 to -1.0%','−1.0 to -0.5%',
                  '-0.5 to 0%','0 to +0.5%','+0.5 to +1.0%','>+1.0%']:
            if b not in spy_buckets:
                # try without minus sign difference
                found = False
                for k in spy_buckets:
                    if b.replace('−','-') == k or k == b:
                        b2 = k; found = True; break
                if not found: continue
            else:
                b2 = b
            pnls = spy_buckets[b2]
            wins = len([p for p in pnls if p > 0])
            avg  = sum(pnls)/len(pnls)
            tot  = sum(p/100*CAPITAL for p in pnls)
            print(f"  {b2:>16}  {len(pnls):>5}  {wins/len(pnls)*100:>5.1f}%  {avg:>+7.2f}%  ${tot:>8.0f}")

        # WR by sector ETF return bucket
        print(f"\n--- Sector ETF day return buckets (signals with sector data) ---")
        sect_buckets = defaultdict(list)
        for s in signals:
            if not s['sector_etf']:
                continue
            date_ret = ret_by_date.get(s['scan_date'], {})
            sect_ret = date_ret.get(s['sector_etf'])
            if sect_ret is None:
                continue
            if sect_ret <= -2.0:   b = '≤-2.0%'
            elif sect_ret <= -1.0: b = '-2.0 to -1.0%'
            elif sect_ret <= -0.5: b = '-1.0 to -0.5%'
            elif sect_ret <= 0:    b = '-0.5 to 0%'
            elif sect_ret <= 0.5:  b = '0 to +0.5%'
            elif sect_ret <= 1.0:  b = '+0.5 to +1.0%'
            else:                   b = '>+1.0%'
            sect_buckets[b].append(s['outcome_5d'])

        print(f"  {'Sect day':>16}  {'n':>5}  {'WR':>6}  {'Avg 5d':>8}  {'Total $':>9}")
        order = ['≤-2.0%','-2.0 to -1.0%','-1.0 to -0.5%','-0.5 to 0%',
                 '0 to +0.5%','+0.5 to +1.0%','>+1.0%']
        for b in order:
            if b not in sect_buckets: continue
            pnls = sect_buckets[b]
            wins = len([p for p in pnls if p > 0])
            avg  = sum(pnls)/len(pnls)
            tot  = sum(p/100*CAPITAL for p in pnls)
            print(f"  {b:>16}  {len(pnls):>5}  {wins/len(pnls)*100:>5.1f}%  {avg:>+7.2f}%  ${tot:>8.0f}")


if __name__ == '__main__':
    main()
