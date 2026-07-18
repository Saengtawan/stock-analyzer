"""The AI's decision — stages 3-5 (classify + select + exit) as one judgment output.

A Claude session reads the v2 context brief and writes plans/decisions/<date>.json.
Code never fabricates this; it only validates + executes it. Empty picks = abstain.

Schema:
{
  "date": "2026-07-15",
  "regime": "AI's one-line read of the tape/day",
  "picks": [
    {"sym": "UNH", "archetype": "gap_down_reversal",
     "reason": "gapped -9% on a guidance cut (idiosyncratic), mega-cap in a healthy",
     "exit_style": "hold_eod",      // hold_eod | trail
     "hard_stop": -4.0,             // % hard stop from entry
     "trail_pct": null},            // required if exit_style == trail
    ...
  ],
  "abstain_reason": null            // string if picks == []
}
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json, os

ARCHETYPES = ("gap_down_reversal", "oversold_bounce", "news_catalyst",
              "earnings_gap_and_go", "rumor_denial_reversal", "breakout", "sympathy_junk", "other")
EXIT_STYLES = ("hold_eod", "trail")


@dataclass
class DecisionPick:
    sym: str
    archetype: str
    reason: str
    exit_style: str = "hold_eod"
    hard_stop: float = -4.0
    trail_pct: float | None = None

    def __post_init__(self):
        self.sym = self.sym.upper()
        if self.exit_style not in EXIT_STYLES:
            raise ValueError(f"exit_style must be {EXIT_STYLES}, got {self.exit_style!r}")
        if self.exit_style == "trail" and not self.trail_pct:
            raise ValueError(f"{self.sym}: trail exit needs trail_pct")
        if self.hard_stop is not None and self.hard_stop >= 0:   # None = hold-EOD, no stop
            raise ValueError(f"{self.sym}: hard_stop must be negative (or null for hold-EOD)")


@dataclass
class Decision:
    date: str
    regime: str = ""
    picks: list = field(default_factory=list)
    abstain_reason: str | None = None

    def to_json(self):
        d = asdict(self)
        return json.dumps(d, indent=2, ensure_ascii=False)

    def save(self, ddir="plans/decisions"):
        os.makedirs(ddir, exist_ok=True)
        path = os.path.join(ddir, f"{self.date}.json")
        with open(path, "w") as f:
            f.write(self.to_json())
        return path

    @classmethod
    def load(cls, date, ddir="plans/decisions"):
        path = os.path.join(ddir, f"{date}.json")
        raw = json.load(open(path))
        picks = [DecisionPick(**p) for p in raw.get("picks", [])]
        return cls(date=raw["date"], regime=raw.get("regime", ""), picks=picks,
                   abstain_reason=raw.get("abstain_reason"))

    @classmethod
    def abstain(cls, date, reason="no decision filed"):
        return cls(date=date, regime="abstain", picks=[], abstain_reason=reason)
