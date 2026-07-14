"""Classify #1 — gap-down reversal.

Mechanism (validated from raw stats, 2024-2026, N=26k liquid gainers):
  A stock that GAPPED DOWN at the open (own bad overnight news, idiosyncratic)
  but has climbed back to GREEN by ~09:36 is showing genuine buy-side demand
  against its own gap. On the descriptive cut, the gap-down-and-recover cohort
  had the best mean of any open-type (+0.38 gross) and the LEAST-bad tail.

  The regime kicker (gap-down + SPY RED morning = +1.56 net, WR 63%) is NOT
  hard-coded here — that lives in the PLAN. The AI enables this classify on
  risk-off / red-tape mornings, where fighting the tape = the strongest signal.
  This module only defines the mechanical archetype + its own exit.

Honest notes:
  - Rank within the setup is LOW signal (we could not beat gain-rank cleanly);
    we rank by gain for simplicity and log that it's near-noise.
  - Numbers are descriptive/in-sample on wf_1min (relative EOD, same-source).
    The per-YEAR picture is NOT "green every year" — judge by expectancy +
    survivable worst year, and let the plan's regime gate do the day-selection.
"""
from __future__ import annotations
from .base import Classify, PositionState
from ..contract import Candidate, Context


class GapDownReversal(Classify):
    name = "gap_down_reversal"
    mechanism = "gapped down on own news, bounced GREEN by 09:36 = real relative strength"

    # --- filter thresholds ---
    GAIN_LO, GAIN_HI = 2.0, 6.0     # must have recovered to a real green move (not froth >6)
    GAP_MAX = -0.5                  # opened at least 0.5% below prev close
    MIN_DOLLAR_VOL = 20e6           # liquidity floor

    # --- exit (this classify's own) ---
    HARD_SL = -4.0                  # hard stop; otherwise hold to EOD
    MIN_HOLD_MIN = 15               # don't stop out on the first-minute noise

    def applies(self, c: Candidate, ctx: Context) -> bool:
        return (self.GAIN_LO <= c.gain < self.GAIN_HI
                and c.gap <= self.GAP_MAX
                and c.dollar_vol >= self.MIN_DOLLAR_VOL)

    def rank_key(self, c: Candidate, ctx: Context) -> float:
        # rank is near-noise within this setup; gain is the simple, honest choice
        return c.gain

    def regime_ok(self, ctx: Context) -> bool:
        # At-open gate: this reversal pays only when the tape is RED (09:36).
        # Fighting a red tape = the real relative-strength tell. On green/flat
        # mornings there's no such signal (validated: red +1.56 vs green +0.10).
        # The pre-open AI plan additionally abstains when the red is driven by
        # bad macro/fed/geo news (real risk-off) — that gate lives in the plan.
        return ctx.spy_red

    def exit(self, st: PositionState) -> str:
        if st.minutes_held >= self.MIN_HOLD_MIN and st.cur_pnl <= self.HARD_SL:
            return "EXIT"
        return "HOLD"   # hold to EOD (engine flattens at 15:55)
