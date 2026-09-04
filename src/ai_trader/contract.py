"""Contract between the AI layer and the rule layer.

`Plan` is the ONLY channel: the AI writes it pre-open, the rule layer reads it
at open. `Candidate` and `Context` are the inputs the rule layer sees at scan.

Kept dependency-free (stdlib only) so both a cron AI job and the backtest can
import it without dragging in the trading engine.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json, os

VALID_RISK = ("normal", "reduced", "abstain")


@dataclass
class Plan:
    """The AI's pre-open decision for the day. See README for the schema."""
    date: str
    regime: str = "unknown"
    enabled_classifies: list[str] = field(default_factory=list)
    risk: str = "normal"                       # normal | reduced | abstain
    max_positions: int = 1
    notes: dict = field(default_factory=dict)  # sym -> free-text (e.g. skip reason)
    generated_by: str = "stub"                 # stub | mechanical | claude

    def __post_init__(self):
        if self.risk not in VALID_RISK:
            raise ValueError(f"risk must be one of {VALID_RISK}, got {self.risk!r}")
        if self.max_positions < 0:
            raise ValueError("max_positions must be >= 0")

    # --- helpers the rule layer uses ---
    def is_enabled(self, classify_name: str) -> bool:
        return classify_name in self.enabled_classifies

    def skip_syms(self) -> set:
        """Symbols the AI flagged to skip (note starts with 'skip' or 'avoid')."""
        out = set()
        for sym, note in self.notes.items():
            n = (note or "").strip().lower()
            if n.startswith("skip") or n.startswith("avoid") or "-> skip" in n:
                out.add(sym.upper())
        return out

    def size_mult(self) -> float:
        return {"normal": 1.0, "reduced": 0.5, "abstain": 0.0}[self.risk]

    # --- io ---
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    def save(self, plans_dir: str = "plans") -> str:
        os.makedirs(plans_dir, exist_ok=True)
        path = os.path.join(plans_dir, f"{self.date}.json")
        with open(path, "w") as f:
            f.write(self.to_json())
        return path

    @classmethod
    def load(cls, date: str, plans_dir: str = "plans") -> "Plan":
        path = os.path.join(plans_dir, f"{date}.json")
        with open(path) as f:
            return cls(**json.load(f))

    @classmethod
    def abstain_default(cls, date: str, reason: str = "no plan generated") -> "Plan":
        """Fail SAFE: if no plan exists for the day, do not trade."""
        return cls(date=date, regime="no_plan", enabled_classifies=[],
                   risk="abstain", notes={"_": reason}, generated_by="fallback")


@dataclass
class Candidate:
    """One morning gainer at decision time (~09:34-36 ET)."""
    sym: str
    gain: float          # % from 09:30 open at decision time
    gap: float           # % open(09:30) vs prev daily close   (<0 = gapped down)
    dollar_vol: float    # trailing ~20d avg $ volume (liquidity)
    price: float = 0.0
    sector: str = ""
    peak_gain: float = 0.0   # max % above 09:30 open seen so far
    extra: dict = field(default_factory=dict)

    @property
    def giveback(self) -> float:
        """How far below the intraday peak it currently sits (path quality)."""
        return max(0.0, self.peak_gain - self.gain)


@dataclass
class Context:
    """Day/market state at decision time — the regime inputs."""
    date: str
    spy_morning: float = 0.0   # SPY % 09:30 -> decision time
    vix: float = 0.0
    n_gainers: int = 0         # breadth proxy
    extra: dict = field(default_factory=dict)

    @property
    def spy_red(self) -> bool:
        return self.spy_morning <= -0.15

    @property
    def spy_green(self) -> bool:
        return self.spy_morning >= 0.15
