#!/usr/bin/env python3
"""decile_scan.py — find signals the MEAN hides (built 2026-06-16).

For every feature, bin the trade population into deciles and look at per-decile
avg/worst/WR. Surfaces signal that mean/correlation tests miss because it lives in:
  - the TAILS (worst-decile vs best-decile contrast, with a monotonicity check)
  - a NONLINEAR shape (U / hump — flat correlation, curved bins)
  - the LEFT tail only (catastrophe marker — predicts worst-trade not avg)
Then runs a FOLD-SPLIT on the top-vs-bottom-decile contrast and only flags features
whose contrast holds in BOTH halves (kills tail-mined false positives).

  python3 scripts/decile_scan.py                  # band 2-3.5 picks (deploy pop), 5 bins
  python3 scripts/decile_scan.py --pop z1all      # all Z1 gain>0 top-1/day
  python3 scripts/decile_scan.py --nbins 10 --feature gap_from_prev   # detail one feature

Reads /tmp/wf_h12a_preds.csv (wp+pnl_EOD per candidate) + features_5yr_noleak.pkl.
Outcome = pnl_EOD (hold-EOD). Read-only. NOT a deploy tool — a discovery scanner; every
flag still needs the full gauntlet (remove-top-N, plateau, mechanism, source-parity).
"""
import sys, argparse, numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
ROOT = '/home/saengtawan/work/project/cc/stock-analyzer'

EXCLUDE = {'sym', 'date', 'zone', 'sector', 'mins_from_open', 'pnl_EOD', 'ret', 'wp_use',
           'ad_ratio', 'dow', 'q', 'win', 'time'}
# outcome-derived / leaky columns (forward returns, trail pnl, any label) — NOT predictors
LEAK_PREFIX = ('label', 'fwd', 'trail', 'fut', 'eod', 'pnl', 'y_', 'target')
def is_leaky(c):
    cl = c.lower()
    return cl.startswith(LEAK_PREFIX) or cl.endswith(('_pnl', '_ret', '_fwd', '_eod', '_label'))

def build(pop):
    P = pd.read_csv('/tmp/wf_h12a_preds.csv')
    f = pd.read_pickle(f'{ROOT}/cache/bt_features/features_5yr_noleak.pkl'); f = f.loc[:, ~f.columns.duplicated()]
    f['date'] = pd.to_datetime(f['date']).dt.strftime('%Y-%m-%d')
    feat_cols = [c for c in f.columns if c not in ('sym', 'date', 'time')]
    P = P.merge(f[['sym', 'date', 'mins_from_open'] + [c for c in feat_cols if c not in P.columns]],
                on=['sym', 'date', 'mins_from_open'], how='left')
    Z = P[(P.zone == 'Z1') & (P.mins_from_open == 5) & (P.gain_from_open > 0)].dropna(subset=['gain_from_open']).copy()
    if pop == 'band':
        Z = Z[(Z.gain_from_open >= 2) & (Z.gain_from_open <= 3.5)]
    # top-1 by gain per day = the trade population
    picks = Z.sort_values('gain_from_open', ascending=False).groupby('date').head(1).copy()
    picks['ret'] = picks['pnl_EOD']; picks['date'] = pd.to_datetime(picks['date'])
    return picks

def bin_stats(df, feat, nb):
    d = df[['date', 'ret', feat]].dropna()
    if d[feat].nunique() < nb:  # low-cardinality
        return None
    try:
        d['bin'] = pd.qcut(d[feat].rank(method='first'), nb, labels=False)
    except Exception:
        return None
    g = d.groupby('bin')
    avg = g.ret.mean().values; wrst = g.ret.min().values; wr = g.ret.apply(lambda a: (a > 0).mean() * 100).values
    fmean = g[feat].mean().values; n = g.size().values
    return d, avg, wrst, wr, fmean, n

def analyze(df, feat, nb):
    r = bin_stats(df, feat, nb)
    if r is None:
        return None
    d, avg, wrst, wr, fmean, n = r
    corr = np.corrcoef(d[feat], d.ret)[0, 1]
    # winner/loser Cohen's d (the mean test)
    w = d[d.ret > 0][feat]; l = d[d.ret <= 0][feat]
    sp = np.sqrt((w.var() + l.var()) / 2); cohen = (w.mean() - l.mean()) / sp if sp > 0 else 0
    tail_spread = avg[-1] - avg[0]                       # top-decile avg minus bottom
    worst_lo, worst_hi = wrst[0], wrst[-1]               # left-tail by bin
    mono = abs(np.corrcoef(np.arange(len(avg)), avg)[0, 1])  # |rank-corr| of bin avgs
    mid = np.mean(avg[1:-1]); ends = (avg[0] + avg[-1]) / 2
    u = mid - ends                                       # <0 hump(mid worse), >0 valley
    # fold-split: top vs bottom decile contrast in each half
    mid_dt = d.date.quantile(0.5)
    def contrast(sub):
        s = sub.dropna(subset=[feat])
        if len(s) < nb * 2: return np.nan
        try: s['b'] = pd.qcut(s[feat].rank(method='first'), nb, labels=False)
        except Exception: return np.nan
        hi = s[s.b == nb - 1].ret.mean(); lo = s[s.b == 0].ret.mean()
        return hi - lo
    fa = contrast(d[d.date < mid_dt]); fb = contrast(d[d.date >= mid_dt])
    fold_ok = (not np.isnan(fa) and not np.isnan(fb) and np.sign(fa) == np.sign(fb) and abs(fa) > 0.1 and abs(fb) > 0.1)
    return dict(feat=feat, n=len(d), corr=corr, cohen=cohen, tail=tail_spread,
                worst_lo=worst_lo, worst_hi=worst_hi, mono=mono, u=u, fa=fa, fb=fb,
                fold_ok=fold_ok, avg=avg, wr=wr, wrst=wrst, fmean=fmean, nb=n)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pop', default='band', choices=['band', 'z1all'])
    ap.add_argument('--nbins', type=int, default=5)
    ap.add_argument('--top', type=int, default=20)
    ap.add_argument('--feature', default=None, help='show one feature in detail')
    a = ap.parse_args()
    df = build(a.pop)
    feats = [c for c in df.columns if c not in EXCLUDE and not is_leaky(c) and df[c].dtype.kind in 'fi']
    print(f"# population={a.pop}  N={len(df)} picks  bins={a.nbins}  features={len(feats)}  outcome=hold-EOD\n")

    if a.feature:
        res = analyze(df, a.feature, a.nbins)
        if not res: print("feature unusable (low cardinality / NaN)"); return
        print(f"=== {a.feature} ===  corr={res['corr']:+.3f} cohenD={res['cohen']:+.2f} "
              f"tail_spread={res['tail']:+.3f} mono={res['mono']:.2f} U={res['u']:+.3f} "
              f"foldA={res['fa']:+.3f} foldB={res['fb']:+.3f} {'FOLD-OK' if res['fold_ok'] else 'fold-FAIL'}")
        print(f"{'bin':>4}{'feat_mu':>10}{'n':>5}{'avg%':>8}{'WR%':>6}{'worst':>8}")
        for i in range(len(res['avg'])):
            print(f"{i:>4}{res['fmean'][i]:>10.3f}{'':>0}{0:>0}{res['avg'][i]:>8.3f}{res['wr'][i]:>6.0f}{res['wrst'][i]:>8.2f}")
        return

    rows = [r for r in (analyze(df, f, a.nbins) for f in feats) if r]
    # hidden_score: tail contrast that the linear corr MISSED, and that holds across folds
    for r in rows:
        hidden = abs(r['tail']) * (1.0 if r['fold_ok'] else 0.0)
        # bonus if mean/corr is weak (genuinely hidden) — penalize if corr already big
        r['hidden'] = hidden * (1.0 - min(abs(r['corr']) / 0.3, 0.8))
        r['catas'] = r['worst_hi'] - r['worst_lo']   # >0 = bottom decile holds the catastrophes
    rows.sort(key=lambda r: -r['hidden'])
    print(f"{'feature':<22}{'corr':>7}{'cohenD':>7}{'tail':>8}{'foldA':>7}{'foldB':>7}{'mono':>6}{'U':>7}{'catas':>7}  flag")
    print('-' * 96)
    for r in rows[:a.top]:
        shape = 'U/hump' if abs(r['u']) > 0.3 and r['mono'] < 0.6 else ('mono' if r['mono'] > 0.7 else '')
        flag = []
        if r['fold_ok'] and abs(r['tail']) > 0.3 and abs(r['corr']) < 0.12: flag.append('★HIDDEN')
        elif r['fold_ok'] and abs(r['tail']) > 0.3: flag.append('signal')
        if r['catas'] > 1.0: flag.append('catas-marker')
        if shape: flag.append(shape)
        print(f"{r['feat']:<22}{r['corr']:>+7.3f}{r['cohen']:>+7.2f}{r['tail']:>+8.3f}"
              f"{r['fa']:>+7.3f}{r['fb']:>+7.3f}{r['mono']:>6.2f}{r['u']:>+7.3f}{r['catas']:>+7.2f}  {' '.join(flag)}")
    print(f"\n★HIDDEN = mean-test missed it (|corr|<0.12) BUT tail-contrast holds in BOTH folds.")
    print(f"catas-marker = bottom decile concentrates the worst trades (left-tail filter candidate).")
    print(f"NOTE: discovery only — every flag still needs remove-top-N + plateau + mechanism + source-parity.")

if __name__ == '__main__':
    main()
