"""
v2 Stage-0 — the honest measuring harness.

EVERY claim in v2 must pass through this. It exists because the absence of an
honest, fixed yardstick let conclusions drift with the conversation (over-claim,
then over-correct). The rules it enforces:

  1. NET of cost      — gross return minus a realistic round-trip cost. Nothing is
                        judged on gross.
  2. Block-bootstrap  — CI on the mean using a MOVING BLOCK (not iid), so serial
                        correlation / vol-clustering doesn't shrink the CI falsely.
  3. Per-fold ALWAYS  — never report only an aggregate. A few-fold-driven story
                        must be visible.
  4. Purged CV        — time-ordered folds with an embargo gap, so overlapping/
                        adjacent labels don't leak between train and test.
  5. Effective N      — report autocorrelation-adjusted N so power is honest.

Interpretation rule baked into the language it prints:
  CI excludes 0  -> "sig"            (detectable)
  CI includes 0  -> "not detectable" (NOT "proven equal" — could be underpowered)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass
class Harness:
    cost_roundtrip: float = 0.30      # % round-trip (entry+exit slippage+spread)
    embargo_days: int = 3
    n_splits: int = 5
    block: int = 10                   # bootstrap block length (≈ holding/autocorr span)
    B: int = 3000
    seed: int = 7
    rng: np.random.RandomState = field(default=None, repr=False)

    def __post_init__(self):
        self.rng = np.random.RandomState(self.seed)

    # ---- core stats ----
    def net(self, gross: np.ndarray) -> np.ndarray:
        return np.asarray(gross, float) - self.cost_roundtrip

    def block_ci(self, x: Sequence[float], alpha: float = 0.05) -> tuple:
        """Moving-block bootstrap CI on the mean (autocorrelation-robust)."""
        x = np.asarray(x, float); n = len(x)
        if n < self.block + 1:
            return (float(np.mean(x)) if n else 0.0, np.nan, np.nan)
        nb = int(np.ceil(n / self.block))
        means = np.empty(self.B)
        for b in range(self.B):
            starts = self.rng.randint(0, n - self.block + 1, nb)
            samp = np.concatenate([x[s:s + self.block] for s in starts])[:n]
            means[b] = samp.mean()
        lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        return (float(x.mean()), float(lo), float(hi))

    @staticmethod
    def eff_n(x: Sequence[float]) -> float:
        """Lag-1 autocorrelation-adjusted effective sample size."""
        x = np.asarray(x, float) - np.mean(x)
        if len(x) < 3:
            return float(len(x))
        r1 = np.corrcoef(x[:-1], x[1:])[0, 1]
        if not np.isfinite(r1) or abs(r1) >= 0.999:
            return float(len(x))
        return float(len(x) * (1 - r1) / (1 + r1))

    # ---- purged CV ----
    def purged_folds(self, dates: Sequence[str]):
        """Yield (train_mask, test_idx) chronological folds with embargo purge."""
        dates = pd.to_datetime(pd.Series(list(dates)).reset_index(drop=True))
        order = np.argsort(dates.values)
        for test_idx in np.array_split(order, self.n_splits):
            t0 = dates.iloc[test_idx].min() - pd.Timedelta(days=self.embargo_days)
            t1 = dates.iloc[test_idx].max() + pd.Timedelta(days=self.embargo_days)
            in_test = np.zeros(len(dates), bool); in_test[test_idx] = True
            within_embargo = (dates.values >= np.datetime64(t0)) & (dates.values <= np.datetime64(t1))
            train_mask = ~in_test & ~within_embargo
            yield train_mask, test_idx

    # ---- reporting ----
    def report(self, ret_gross: Sequence[float], dates: Sequence[str], label: str = '',
               quarterly: bool = True) -> dict:
        """Net-of-cost mean + block-CI + per-quarter + eff-N. Prints and returns dict."""
        net = self.net(ret_gross)
        m, lo, hi = self.block_ci(net)
        en = self.eff_n(net)
        verdict = '>0 sig' if (np.isfinite(lo) and lo > 0) else 'not detectable'
        print(f"[{label}] net avg={m:+.3f}  block-CI[{lo:+.3f},{hi:+.3f}]  "
              f"N={len(net)} effN={en:.0f}  -> {verdict}")
        out = {'mean': m, 'ci': (lo, hi), 'n': len(net), 'eff_n': en, 'sig': bool(lo > 0) if np.isfinite(lo) else False}
        if quarterly:
            q = pd.to_datetime(pd.Series(list(dates))).dt.to_period('Q').astype(str).values
            pq = pd.DataFrame({'q': q, 'net': net}).groupby('q')['net'].mean()
            print('   per-Q: ' + '  '.join(f'{k}:{v:+.2f}' for k, v in pq.items()) +
                  f'  (Q+:{(pq > 0).sum()}/{len(pq)})')
            out['per_q'] = pq.to_dict()
        return out

    def cv_meta_filter(self, df: pd.DataFrame, feats: list, y_col: str, ret_col: str,
                       model_factory: Callable, thresholds=(0.5,), date_col: str = 'date') -> None:
        """Purged-CV meta-filter eval: OOF preds, then net-of-cost of kept bets vs trade-all."""
        df = df.reset_index(drop=True)
        oof = np.full(len(df), np.nan)
        for train_mask, test_idx in self.purged_folds(df[date_col].values):
            tr = df[train_mask]
            m = model_factory(); m.fit(tr[feats].astype(float).values, tr[y_col].values)
            oof[test_idx] = m.predict_proba(df.iloc[test_idx][feats].astype(float).values)[:, 1]
        df = df.assign(_p=oof)
        self.report(df[ret_col].values, df[date_col].values, label='trade-all')
        for t in thresholds:
            k = df[df._p >= t]
            if len(k) < 30:
                continue
            self.report(k[ret_col].values, k[date_col].values, label=f'filter p>={t} (keep {len(k)}/{len(df)})')


def get_harness(**kw) -> Harness:
    return Harness(**kw)
