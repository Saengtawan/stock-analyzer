"""riser_momentum — Z1 morning-riser lane (rank by gain, not win_p).

THESIS (designed + backtested 2026-06-11/12, user-driven)
---------------------------------------------------------
Among the H12-A Z1 candidates (cell-ok, win_p>=thr, mfo 0-9 = 09:30-09:39),
the model's win_p favors stable/defensive names that DON'T pop. The names that
actually run intraday are the RISERS — highest `gain_from_open` at scan. Picking
the top-1 by gain (instead of win_p) captures the movers the model under-weights.

This is ORTHOGONAL to H12-A: same candidate pool, different #1 selection. It does
NOT touch ml_filter / H12-A — it re-ranks the already-filtered Z1 candidates.

BACKTEST (Z1 holdout 2025-05+, top-1/day, phase0 + intraday_bars_5m peak)
-------------------------------------------------------------------------
WIN = peak >= +1% after entry.
  rank by gain   : WR 73%  avgPeak +2.65%  avgEOD +0.61%   (5/5 quarters) <-- THIS
  rank by win_p  : WR 60%  avgPeak +1.98%  avgEOD +0.29%   (old system)
  gain x beta    : WR 71%  (beta adds nothing — gain self-selects high-beta)
gain-top picks are 93% "still at high" (from_peak > -0.5) — the rank auto-avoids
faded peaks (a faded stock's current gain is lower, so it isn't #1).

KNOBS DELIBERATELY OMITTED (each tested, none helped):
  - no beta filter (gain captures it)        - no VIX gate (riser wins across VIX)
  - no from_peak filter (gain self-selects)  - no TP (win = peak>=1%, hold else)

ENTRY: BUY at display time (~09:38, on decision) — the backtest entry = scan-time
(gain_from_open at the pick moment), so buy-on-display matches what was validated.
Do NOT wait for a 09:40 pullback: it was an unvalidated add-on (06-11 dipped ~1-2%,
but waiting risks missing the runner; the wait-1-bar edge is only +0.03%/pick).

STATUS: RESEARCH / paper-pending. NOT auto-registered in engine. Backtest only —
13-month holdout, intraday_bars_5m peak (relative ok, absolute approximate), modest
EOD (+0.61%) with the edge concentrated in the intraday peak. Forward-validate before
any live use. Reversible: it reads ml_filter output; delete this file to remove.
"""
from __future__ import annotations
from datetime import datetime
import pytz

from .base import BaseStrategy, ScanResult, Pick
from .ml_filter import MLFilterStrategy

ET = pytz.timezone('US/Eastern')

# Z1 = mfo 0-9 (09:30-09:39). The riser lane only operates in the Z1 window.
Z1_MFO_MAX = 9


class RiserMomentumStrategy(BaseStrategy):
    name = "riser_momentum"
    description = "Z1 morning riser — rank H12-A Z1 candidates by gain_from_open, buy top-1"
    # Z1 window = mfo 0-9 (09:30-09:39). Run in this window; BUY at display (~09:38, on decision) — see ENTRY in docstring.
    # At/after 09:40 (mfo>=10) candidates are Z2, not Z1 — riser lane is Z1-only.
    time_start = "09:30"
    time_end = "09:39"
    expected_wr = 0.73          # WR(peak>=1%) on backtest
    expected_ev = 0.0061        # avg EOD if held (peak edge is larger: +2.65%)

    def scan(self) -> ScanResult:
        now_et = datetime.now(ET)
        ts = now_et.strftime('%Y-%m-%d %H:%M:%S %Z')
        mfo = (now_et.hour - 9) * 60 + (now_et.minute - 30)

        import os as _os
        if _os.environ.get('RISER_ENABLED', '1') != '1':
            return ScanResult(self.name, ts, 'skipped_gate', reason="RISER_ENABLED=0 (disabled)")

        # Z1 window only: mfo 0-9. Outside that the candidate pool is a different zone.
        if not (0 <= mfo <= 9):
            return ScanResult(self.name, ts, 'out_of_window',
                              reason=f"riser lane = Z1 only (mfo {mfo} not in 0-9; run 09:30-09:39 ET)")

        # Reuse H12-A candidate generation. ml_filter stashes the full passing
        # candidate list on self.last_all_candidates (hook added 2026-06-12).
        # At a Z1-window scan, ALL candidates are Z1 (single mfo per scan).
        ml = MLFilterStrategy()
        ml.scan()  # populates ml.last_all_candidates (status side-effects ignored)
        cands = getattr(ml, 'last_all_candidates', None) or []

        # Riser = a name that's actually up at scan (gain > 0). NO win_p filter
        # (user decision 2026-06-12: unfiltered pool — recent-fold WR(peak>=1) 69 vs 64
        # and avgPeak +3.08 vs +2.65 beat the wp>=0.68 pool; EOD-hold weaker, accepted).
        z1 = [c for c in cands if (c.extra.get('gain_pct') or -99) > 0]
        if not z1:
            return ScanResult(self.name, ts, 'no_picks',
                              reason="no Z1 riser candidate (none cell-ok+up this scan)",
                              metadata={'mfo': mfo, 'n_candidates': len(cands)})

        # RANK BY GAIN (the whole point) — top-1 riser still at its high.
        top = max(z1, key=lambda c: c.extra.get('gain_pct', 0))
        top.reason = (f"RISER gain+{top.extra.get('gain_pct'):.1f}% "
                      f"(win_p={top.extra.get('ml_prob'):.2f}) {top.extra.get('sector', '')[:8]} "
                      f"β{top.extra.get('beta')} — rank-by-gain top-1 | win=peak>=1%")
        return ScanResult(self.name, ts, 'active',
                          reason=f"top riser by gain among {len(z1)} Z1 candidates",
                          picks=[top], regime=f"mfo={mfo}",
                          metadata={'n_z1_risers': len(z1),
                                    'ranking': 'gain_from_open',
                                    'win_metric': 'peak>=1%'})
