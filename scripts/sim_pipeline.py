#!/usr/bin/env python3
"""
Discovery Pipeline Walk-Forward Sim v15.3
==========================================
Full pipeline: MacroKernel → StockKernel → 4 strategies → filters → rank → D0-D3 exit.

Purpose: Measure REAL WR from kernel-selected picks vs random selection.
This answers: does the Discovery pipeline add alpha over random picking?

Walk-forward: expanding window (all data before test month).
Kernels: Gaussian kernel regression (Nadaraya-Watson), same as production.
Strategies: DIP, OVERSOLD, VALUE, CONTRARIAN (same rules as multi_strategy.py).
Exit: D0-D3 dynamic TP (0.55/0.55/0.85/1.09 × ATR), SL=0.8×ATR (1.5-3.5%).
"""
import sqlite3
import numpy as np
from pathlib import Path
from collections import defaultdict

DB = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# === Config (v15.3) ===
PER_TRADE = 500
COMMISSION = 0.50
SLIPPAGE = 0.10  # %
MAX_PER_STRATEGY = 2
MAX_TOTAL = 8
MIN_MCAP_B = 30  # $30B
MAX_VOL_RATIO = 3.0


# === Data Loading ===

def load_all():
    """Load signals + D0-D3 daily bars + macro + fundamentals."""
    conn = None  # via get_session())

    signals = conn.execute("""
        SELECT b.scan_date, b.symbol, b.sector, b.scan_price,
               b.atr_pct, b.momentum_5d, b.momentum_20d,
               b.distance_from_20d_high, b.volume_ratio, b.vix_at_signal,
               b.outcome_5d, b.outcome_1d, b.outcome_3d,
               -- macro (13-20)
               COALESCE(m.vix_close, 20), m.spy_close, m.crude_close,
               COALESCE(m.vix3m_close, 22), m.yield_10y,
               mb.pct_above_20d_ma, mb.new_52w_lows, mb.new_52w_highs,
               -- D0 bars (21-24)
               d0.open, d0.high, d0.low, d0.close,
               -- D1 bars (25-28)
               d1.open, d1.high, d1.low, d1.close,
               -- D2 bars (29-32)
               d2.open, d2.high, d2.low, d2.close,
               -- D3 bars (33-36)
               d3.open, d3.high, d3.low, d3.close,
               -- sector 1d (37)
               COALESCE(ser.pct_change, 0)
        FROM backfill_signal_outcomes b
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%%w', b.scan_date) = '6' THEN date(b.scan_date, '-1 day')
                WHEN strftime('%%w', b.scan_date) = '0' THEN date(b.scan_date, '-2 days')
                ELSE b.scan_date END
        LEFT JOIN market_breadth mb
            ON mb.date = CASE
                WHEN strftime('%%w', b.scan_date) = '6' THEN date(b.scan_date, '-1 day')
                WHEN strftime('%%w', b.scan_date) = '0' THEN date(b.scan_date, '-2 days')
                ELSE b.scan_date END
        JOIN signal_daily_bars d0
            ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
        JOIN signal_daily_bars d1
            ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
        JOIN signal_daily_bars d2
            ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
        JOIN signal_daily_bars d3
            ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
        LEFT JOIN sector_etf_daily_returns ser
            ON ser.sector = b.sector
            AND ser.date = CASE
                WHEN strftime('%%w', b.scan_date) = '6' THEN date(b.scan_date, '-1 day')
                WHEN strftime('%%w', b.scan_date) = '0' THEN date(b.scan_date, '-2 days')
                ELSE b.scan_date END
        WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d0.open > 0
        ORDER BY b.scan_date
    """).fetchall()

    funds = {}
    for r in conn.execute("SELECT symbol, beta, pe_forward, market_cap FROM stock_fundamentals"):
        funds[r[0]] = {'beta': r[1] or 1, 'pe': r[2], 'mcap': r[3] or 1e9}

    # Precompute crude_change_5d per date
    crude_lag = {}
    for r in conn.execute("""
        SELECT date, crude_close,
               LAG(crude_close, 5) OVER (ORDER BY date) as crude_5d_ago
        FROM macro_snapshots WHERE crude_close IS NOT NULL
    """):
        if r[2] and r[2] > 0:
            crude_lag[r[0]] = (r[1] / r[2] - 1) * 100
        else:
            crude_lag[r[0]] = 0

    conn.close()
    return signals, funds, crude_lag


# === Column Indices ===
# 0:scan_date 1:symbol 2:sector 3:scan_price 4:atr_pct 5:momentum_5d
# 6:momentum_20d 7:distance_from_20d_high 8:volume_ratio 9:vix_at_signal
# 10:outcome_5d 11:outcome_1d 12:outcome_3d
# 13:vix 14:spy 15:crude 16:vix3m 17:yield_10y
# 18:breadth(pct_above_20d_ma) 19:new_52w_lows 20:new_52w_highs
# 21:d0_open 22:d0_high 23:d0_low 24:d0_close
# 25:d1_open 26:d1_high 27:d1_low 28:d1_close
# 29:d2_open 30:d2_high 31:d2_low 32:d2_close
# 33:d3_open 34:d3_high 35:d3_low 36:d3_close
# 37:sector_1d_change

I_DATE, I_SYM, I_SEC, I_PRICE = 0, 1, 2, 3
I_ATR, I_MOM5, I_MOM20, I_D20H, I_VOL, I_VIX_SIG = 4, 5, 6, 7, 8, 9
I_OUT5, I_OUT1, I_OUT3 = 10, 11, 12
I_VIX, I_SPY, I_CRUDE, I_VIX3M, I_Y10 = 13, 14, 15, 16, 17
I_BREADTH, I_LOWS, I_HIGHS = 18, 19, 20
I_D0O, I_D0H, I_D0L, I_D0C = 21, 22, 23, 24
I_D1O, I_D1H, I_D1L, I_D1C = 25, 26, 27, 28
I_D2O, I_D2H, I_D2L, I_D2C = 29, 30, 31, 32
I_D3O, I_D3H, I_D3L, I_D3C = 33, 34, 35, 36
I_SEC1D = 37


# === Inline Kernel ===

class GaussianKernel:
    """Nadaraya-Watson kernel regression — same as KernelEstimator in production."""

    MAX_TRAIN = 40000  # cap training size for memory efficiency

    def __init__(self, bandwidth):
        self.bw = bandwidth
        self.X = None
        self.y = None
        self.means = None
        self.stds = None

    def fit(self, features, returns):
        X = np.array(features, dtype=np.float64)
        y = np.array(returns, dtype=np.float64)
        # Subsample if too large (keep most recent)
        if len(X) > self.MAX_TRAIN:
            X = X[-self.MAX_TRAIN:]
            y = y[-self.MAX_TRAIN:]
        self.means = X.mean(axis=0)
        self.stds = X.std(axis=0)
        self.stds[self.stds == 0] = 1.0
        self.X = (X - self.means) / self.stds
        self.y = y

    def estimate_batch(self, X_new_raw):
        """Vectorized estimation. Uses scipy.cdist for memory efficiency."""
        if self.X is None or len(self.X) == 0:
            return np.zeros(len(X_new_raw))

        from scipy.spatial.distance import cdist
        X_new = (np.array(X_new_raw, dtype=np.float64) - self.means) / self.stds
        dists = cdist(X_new, self.X)  # (N_new, N_train)
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum(axis=1)
        total_w[total_w < 1e-10] = 1e-10
        er = (weights @ self.y) / total_w
        return er


# === Strategy Classification ===

def classify_strategies(sig, funds, worst_sector=None):
    """Classify signal into strategies. Returns list of strategy names."""
    sym = sig[I_SYM]
    mom5 = sig[I_MOM5] or 0
    mom20 = sig[I_MOM20] or 0
    d20h = sig[I_D20H] or 0
    vol = sig[I_VOL] or 1
    f = funds.get(sym, {})
    beta = f.get('beta', 1) or 1
    pe = f.get('pe')
    mcap = (f.get('mcap', 1e9) or 1e9)

    strategies = []

    # DIP: -3% to -15%, beta < 1.5
    if -15 < mom5 < -3 and beta < 1.5 and vol > 0.3:
        strategies.append('DIP')

    # OVERSOLD: extreme dip
    if mom5 < -5 and d20h < -10 and beta < 2.0:
        strategies.append('OVERSOLD')

    # VALUE: cheap quality
    if pe and 3 < pe < 15 and beta < 1.5 and mcap > 5e9 and mom5 > -10:
        strategies.append('VALUE')

    # CONTRARIAN: stock in worst sector
    if worst_sector and sig[I_SEC] == worst_sector and beta < 1.5 and mom5 > -15:
        strategies.append('CONTRARIAN')

    return strategies


# === Trade Simulation ===

def sim_d0d3(sig, atr):
    """Simulate D0-D3 trade with dynamic TP. Entry at D0 open. Returns pct return."""
    entry = sig[I_D0O]
    if entry <= 0:
        return 0.0

    sl = max(1.5, min(3.5, 0.8 * atr))
    # Dynamic TP per day (v15.3, validated 30% hit rate each day)
    tps = [
        max(1.0, 0.55 * atr),  # D0
        max(1.0, 0.55 * atr),  # D1
        max(1.5, 0.85 * atr),  # D2
        max(1.5, 1.09 * atr),  # D3
    ]

    day_bars = [
        (sig[I_D0H], sig[I_D0L]),
        (sig[I_D1H], sig[I_D1L]),
        (sig[I_D2H], sig[I_D2L]),
        (sig[I_D3H], sig[I_D3L]),
    ]

    for (h, l), tp in zip(day_bars, tps):
        pct_low = (l / entry - 1) * 100
        pct_high = (h / entry - 1) * 100
        if pct_low <= -sl:
            return -sl
        if pct_high >= tp:
            return tp

    # D3 close exit
    return (sig[I_D3C] / entry - 1) * 100


def exec_trade(sig, atr):
    """Execute trade, return (pnl_dollar, net_return_pct)."""
    ret = sim_d0d3(sig, atr)
    cost = SLIPPAGE * 2 + COMMISSION / PER_TRADE * 100
    net = ret - cost
    pnl = PER_TRADE * net / 100
    return pnl, net


# === Macro Feature Builder ===

def build_macro_vec(sig, crude_lag):
    """Build 8-feature macro vector for kernel. Returns list or None if missing."""
    date = sig[I_DATE]
    vix = sig[I_VIX]
    spy = sig[I_SPY]
    crude = sig[I_CRUDE]
    vix3m = sig[I_VIX3M]
    y10 = sig[I_Y10]
    breadth = sig[I_BREADTH]
    lows = sig[I_LOWS]
    highs = sig[I_HIGHS]

    if any(v is None for v in [spy, crude, y10, breadth, lows, highs]):
        return None

    crude_chg = crude_lag.get(date, 0)
    vix_spread = (vix or 20) - (vix3m or 22)

    return [lows, crude_chg, breadth, highs, y10, spy, crude, vix_spread]


def build_stock_vec(sig, macro_vec):
    """Build 13-feature stock vector (8 macro + 5 stock). Returns list or None."""
    atr = sig[I_ATR]
    mom5 = sig[I_MOM5]
    d20h = sig[I_D20H]
    vol = sig[I_VOL]
    sec1d = sig[I_SEC1D]

    if any(v is None for v in [atr, mom5, d20h, vol]):
        return None

    return macro_vec + [atr, mom5 or 0, d20h or 0, vol or 1, sec1d or 0]


# === Main Simulation ===

def main():
    signals, funds, crude_lag = load_all()
    print(f"Loaded {len(signals):,} signals with D0-D3 bars\n")

    # Group by month
    by_month = defaultdict(list)
    for sig in signals:
        by_month[sig[I_DATE][:7]].append(sig)
    months = sorted(by_month.keys())
    print(f"Date range: {months[0]} to {months[-1]} ({len(months)} months)")
    print(f"Walk-forward: skip first 12 months for training\n")

    # Results accumulators
    pipe_monthly, rand_monthly, topvol_monthly = [], [], []
    pipe_tot = {'t': 0, 'w': 0, 'p': 0.0}
    rand_tot = {'t': 0, 'w': 0, 'p': 0.0}
    topvol_tot = {'t': 0, 'w': 0, 'p': 0.0}
    strat_stats = defaultdict(lambda: {'t': 0, 'w': 0, 'p': 0.0})
    regime_stats = defaultdict(lambda: {'t': 0, 'w': 0, 'p': 0.0})
    kernel_er_vs_actual = []  # (predicted E[R], actual return) pairs

    header = (f"{'Mo':8s} {'Pipe$':>7s} {'PWR':>5s} {'PN':>4s}  "
              f"{'TopV$':>7s} {'TWR':>5s} {'TN':>4s}  "
              f"{'Rand$':>7s} {'RWR':>5s} {'RN':>4s}  "
              f"{'Regime':>6s} {'MacER':>6s}")
    print(header)
    print("-" * len(header))

    # Expanding window: accumulate training AFTER testing each month
    train_macro_feats = []
    train_macro_rets = []
    train_stock_feats = []
    train_stock_rets = []

    rng = np.random.RandomState(42)

    def accumulate_month(month_sigs):
        """Add a month's signals to training pool."""
        for sig in month_sigs:
            mv = build_macro_vec(sig, crude_lag)
            if mv and sig[I_OUT5] is not None:
                train_macro_feats.append(mv)
                train_macro_rets.append(sig[I_OUT5])
                sv = build_stock_vec(sig, mv)
                if sv:
                    train_stock_feats.append(sv)
                    train_stock_rets.append(sig[I_OUT5])

    for mi, month in enumerate(months):
        if mi < 12:
            # Only accumulate, don't test
            accumulate_month(by_month[month])
            continue

        if len(train_macro_feats) < 500:
            accumulate_month(by_month[month])
            continue

        # Fit kernels on all accumulated data (everything BEFORE this month)
        macro_kernel = GaussianKernel(bandwidth=0.4)
        macro_kernel.fit(train_macro_feats, train_macro_rets)

        stock_kernel = GaussianKernel(bandwidth=1.0)
        if len(train_stock_feats) >= 500:
            stock_kernel.fit(train_stock_feats, train_stock_rets)
        else:
            stock_kernel = None

        # Test month
        test_sigs = by_month[month]
        by_day = defaultdict(list)
        for sig in test_sigs:
            by_day[sig[I_DATE]].append(sig)

        pipe_pnl, pipe_t, pipe_w = 0.0, 0, 0
        rand_pnl, rand_t, rand_w = 0.0, 0, 0
        topvol_pnl, topvol_t, topvol_w = 0.0, 0, 0
        month_regime = ''
        month_macro_er = 0

        for day, day_sigs in sorted(by_day.items()):
            if not day_sigs:
                continue

            # Build macro features for this day
            s0 = day_sigs[0]
            mv = build_macro_vec(s0, crude_lag)
            if mv is None:
                continue

            # Macro kernel → E[R] + regime
            macro_er = float(macro_kernel.estimate_batch([mv])[0])
            if macro_er > 0.5:
                regime = 'BULL'
            elif macro_er < -0.5:
                regime = 'CRISIS'
            else:
                regime = 'STRESS'
            month_regime = regime
            month_macro_er = macro_er

            # Find worst sector (for CONTRARIAN)
            sector_moms = defaultdict(list)
            for sig in day_sigs:
                sec = sig[I_SEC]
                if sec:
                    sector_moms[sec].append(sig[I_MOM5] or 0)
            sector_avg = {s: np.mean(ms) for s, ms in sector_moms.items()
                          if len(ms) >= 3}
            worst_sector = min(sector_avg, key=sector_avg.get) if sector_avg else None

            # === PIPELINE: Score + Filter + Strategy + Rank ===

            # Build stock features for all eligible signals
            eligible = []
            stock_vecs = []
            for sig in day_sigs:
                sym = sig[I_SYM]
                mcap_b = (funds.get(sym, {}).get('mcap', 1e9) or 1e9) / 1e9
                vol = sig[I_VOL] or 1

                # v15.3 quality filters
                if mcap_b < MIN_MCAP_B:
                    continue
                if vol > MAX_VOL_RATIO:
                    continue

                sv = build_stock_vec(sig, mv)
                if sv is None:
                    continue

                eligible.append(sig)
                stock_vecs.append(sv)

            if not eligible:
                continue

            # Stock kernel → per-stock E[R]
            if stock_kernel and stock_vecs:
                stock_ers = stock_kernel.estimate_batch(stock_vecs)
            else:
                stock_ers = np.zeros(len(eligible))

            # Score + strategy classify + filter
            scored = []
            for i, sig in enumerate(eligible):
                ser = float(stock_ers[i])

                # Record for correlation analysis
                actual_ret = sim_d0d3(sig, sig[I_ATR] or 2)
                kernel_er_vs_actual.append((ser, actual_ret))

                # Filter: skip negative stock E[R]
                if ser < 0:
                    continue

                strats = classify_strategies(sig, funds, worst_sector)
                if not strats:
                    continue

                scored.append((ser, sig, strats))

            # Rank by volume_ratio desc (proven in sim)
            scored.sort(key=lambda x: -(x[1][I_VOL] or 0))

            # Pick: max 2 per strategy, max 8 total
            strat_count = defaultdict(int)
            pipe_selected = []
            for er, sig, strats in scored:
                if len(pipe_selected) >= MAX_TOTAL:
                    break
                for strat in strats:
                    if strat_count[strat] < MAX_PER_STRATEGY:
                        strat_count[strat] += 1
                        pipe_selected.append((strat, sig, er))
                        break

            # Execute pipeline trades
            for strat, sig, er in pipe_selected:
                atr = sig[I_ATR] or 2
                pnl, net = exec_trade(sig, atr)
                pipe_pnl += pnl
                pipe_t += 1
                if net > 0:
                    pipe_w += 1
                strat_stats[strat]['t'] += 1
                strat_stats[strat]['p'] += pnl
                if net > 0:
                    strat_stats[strat]['w'] += 1
                regime_stats[regime]['t'] += 1
                regime_stats[regime]['p'] += pnl
                if net > 0:
                    regime_stats[regime]['w'] += 1

            # === TOP-VOLUME BASELINE: mcap≥30B, top 8 by volume (no kernel) ===
            topvol_picks = sorted(eligible, key=lambda s: -(s[I_VOL] or 0))[:MAX_TOTAL]
            for sig in topvol_picks:
                atr = sig[I_ATR] or 2
                pnl, net = exec_trade(sig, atr)
                topvol_pnl += pnl
                topvol_t += 1
                if net > 0:
                    topvol_w += 1

            # === RANDOM BASELINE: mcap≥30B, random 8 ===
            n_rand = min(MAX_TOTAL, len(eligible))
            rand_idx = rng.choice(len(eligible), n_rand, replace=False)
            for idx in rand_idx:
                sig = eligible[idx]
                atr = sig[I_ATR] or 2
                pnl, net = exec_trade(sig, atr)
                rand_pnl += pnl
                rand_t += 1
                if net > 0:
                    rand_w += 1

        # Monthly output
        pwr = pipe_w / pipe_t * 100 if pipe_t else 0
        twr = topvol_w / topvol_t * 100 if topvol_t else 0
        rwr = rand_w / rand_t * 100 if rand_t else 0

        print(f"{month:8s} {pipe_pnl:>+7.0f} {pwr:4.0f}% {pipe_t:>3d}  "
              f"{topvol_pnl:>+7.0f} {twr:4.0f}% {topvol_t:>3d}  "
              f"{rand_pnl:>+7.0f} {rwr:4.0f}% {rand_t:>3d}  "
              f"{month_regime:>6s} {month_macro_er:>+5.2f}%")

        pipe_monthly.append(pipe_pnl)
        rand_monthly.append(rand_pnl)
        topvol_monthly.append(topvol_pnl)
        pipe_tot['t'] += pipe_t; pipe_tot['w'] += pipe_w; pipe_tot['p'] += pipe_pnl
        rand_tot['t'] += rand_t; rand_tot['w'] += rand_w; rand_tot['p'] += rand_pnl
        topvol_tot['t'] += topvol_t; topvol_tot['w'] += topvol_w; topvol_tot['p'] += topvol_pnl

        # Accumulate this month for future training
        accumulate_month(by_month[month])

    # === SUMMARY ===
    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80)

    def summarize(label, monthly, tot):
        n = len(monthly)
        if not n or not tot['t']:
            return
        avg = np.mean(monthly)
        std = max(np.std(monthly), 0.01)
        sharpe = avg / std * np.sqrt(12)
        wr = tot['w'] / tot['t'] * 100
        er = tot['p'] / tot['t']
        win_mo = sum(1 for m in monthly if m > 0)
        worst = min(monthly)
        best = max(monthly)
        print(f"\n  {label}")
        print(f"  {'Trades':<20s} {tot['t']:>8,}")
        print(f"  {'Win Rate':<20s} {wr:>7.1f}%")
        print(f"  {'E[R]/trade':<20s} ${er:>+7.2f}")
        print(f"  {'$/mo avg':<20s} ${avg:>+7.0f}")
        print(f"  {'Sharpe (annual)':<20s} {sharpe:>8.2f}")
        print(f"  {'Win months':<20s} {win_mo}/{n} ({win_mo/n*100:.0f}%)")
        print(f"  {'Worst month':<20s} ${worst:>+7.0f}")
        print(f"  {'Best month':<20s} ${best:>+7.0f}")
        print(f"  {'Total PnL':<20s} ${sum(monthly):>+8.0f}")
        # $/mo per $100K capital (8 picks × $500 = $4K active, but annualized)
        print(f"  {'฿100K equiv/mo':<20s} ฿{avg * 100000 / (MAX_TOTAL * PER_TRADE):>+,.0f}")

    summarize("PIPELINE (Kernel + Strategy + Filter + Rank)", pipe_monthly, pipe_tot)
    summarize("TOP-VOLUME (mcap≥30B, top 8 by vol, no kernel)", topvol_monthly, topvol_tot)
    summarize("RANDOM (mcap≥30B, random 8)", rand_monthly, rand_tot)

    # Pipeline vs Random delta
    if pipe_monthly and rand_monthly:
        delta = [p - r for p, r in zip(pipe_monthly, rand_monthly)]
        pipe_better = sum(1 for d in delta if d > 0)
        print(f"\n  PIPELINE vs RANDOM")
        print(f"  {'Pipeline wins':<20s} {pipe_better}/{len(delta)} months")
        print(f"  {'Avg delta/mo':<20s} ${np.mean(delta):>+7.0f}")

    # Per-strategy breakdown
    print(f"\n  PER-STRATEGY BREAKDOWN (Pipeline)")
    print(f"  {'Strategy':<15s} {'N':>6s} {'WR%':>6s} {'$/trade':>9s} {'PnL':>9s}")
    for strat in ['DIP', 'OVERSOLD', 'VALUE', 'CONTRARIAN']:
        st = strat_stats.get(strat, {'t': 0, 'w': 0, 'p': 0})
        if st['t'] > 0:
            wr = st['w'] / st['t'] * 100
            pt = st['p'] / st['t']
            print(f"  {strat:<15s} {st['t']:>6,} {wr:>5.1f}% ${pt:>+8.2f} ${st['p']:>+8.0f}")

    # Per-regime breakdown
    print(f"\n  PER-REGIME BREAKDOWN (Pipeline)")
    print(f"  {'Regime':<10s} {'N':>6s} {'WR%':>6s} {'$/trade':>9s} {'PnL':>9s}")
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        st = regime_stats.get(regime, {'t': 0, 'w': 0, 'p': 0})
        if st['t'] > 0:
            wr = st['w'] / st['t'] * 100
            pt = st['p'] / st['t']
            print(f"  {regime:<10s} {st['t']:>6,} {wr:>5.1f}% ${pt:>+8.2f} ${st['p']:>+8.0f}")

    # Kernel E[R] predictive power
    if kernel_er_vs_actual:
        ers = np.array([x[0] for x in kernel_er_vs_actual])
        acts = np.array([x[1] for x in kernel_er_vs_actual])
        # Information Coefficient (rank correlation)
        from scipy.stats import spearmanr
        ic, p_val = spearmanr(ers, acts)
        # Quintile analysis
        n = len(ers)
        q_idx = np.argsort(ers)
        q_size = n // 5
        print(f"\n  KERNEL PREDICTIVE POWER")
        print(f"  {'IC (Spearman)':<20s} {ic:>8.4f} (p={p_val:.4f})")
        print(f"\n  Quintile Analysis (stock kernel E[R] → actual D0-D3 return):")
        print(f"  {'Quintile':<12s} {'AvgE[R]':>8s} {'AvgActual':>10s} {'WR%':>6s} {'N':>6s}")
        for qi in range(5):
            start = qi * q_size
            end = (qi + 1) * q_size if qi < 4 else n
            idx = q_idx[start:end]
            avg_er = np.mean(ers[idx])
            avg_act = np.mean(acts[idx])
            wr = np.mean(acts[idx] > 0) * 100
            print(f"  Q{qi+1} {'(low)' if qi==0 else '(high)' if qi==4 else '':>6s}  "
                  f"{avg_er:>+7.3f}% {avg_act:>+9.3f}% {wr:>5.1f}% {len(idx):>5d}")


if __name__ == '__main__':
    main()
