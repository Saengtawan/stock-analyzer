"""
Scan engine — dispatches `scan` commands to the right strategy.

Usage:
    from src.scan.engine import run_scan
    result = run_scan('morning_drive')
    result = run_scan('auto')  # auto-select by time/regime

Command routing:
    scan morning_drive  → MorningDriveStrategy
    scan auto           → best strategy for current ET + regime
    scan list           → show available strategies
"""
from datetime import datetime
import pytz

from .strategies.base import ScanResult
from .strategies.orb_prep import OrbPrepStrategy
from .strategies.morning_drive import MorningDriveStrategy
from .strategies.afternoon_strict import AfternoonStrictStrategy
from .strategies.crisis_reversal import CrisisReversalStrategy
from .strategies.ovn_gap import OvernightGapStrategy
from .strategies.fri_mon import FriMonStrategy

ET = pytz.timezone('US/Eastern')

# Registry of available strategies
STRATEGIES = {
    'orb_prep':         OrbPrepStrategy,
    'morning_drive':    MorningDriveStrategy,
    'afternoon_strict': AfternoonStrictStrategy,
    'crisis_reversal':  CrisisReversalStrategy,
    'ovn_gap':          OvernightGapStrategy,
    'fri_mon':          FriMonStrategy,
}


def list_strategies() -> list:
    """Return metadata about all registered strategies."""
    out = []
    for name, cls in STRATEGIES.items():
        s = cls()
        out.append({
            'name': name,
            'description': s.description,
            'time_window': f"{s.time_start}-{s.time_end} ET",
            'expected_wr': s.expected_wr,
            'expected_ev': s.expected_ev,
            'version': s.version,
        })
    return out


def auto_select_strategy() -> str:
    """Pick best strategy for current ET time.

    Priority:
    1. Check which strategies' time windows match current ET
    2. If multiple match, pick highest expected_ev
    3. If none match, return 'morning_drive' as fallback hint
    """
    now_et = datetime.now(ET).strftime("%H:%M")
    candidates = []
    for name, cls in STRATEGIES.items():
        s = cls()
        if s.time_start <= now_et <= s.time_end:
            candidates.append((name, s.expected_ev))
    if not candidates:
        return 'morning_drive'  # fallback
    candidates.sort(key=lambda x: -x[1])
    return candidates[0][0]


def run_scan(command: str = 'auto') -> ScanResult:
    """Run a scan by strategy name or 'auto'."""
    if command == 'auto':
        command = auto_select_strategy()
    if command not in STRATEGIES:
        return ScanResult(
            strategy=command,
            timestamp_et=datetime.now(ET).strftime("%H:%M"),
            status='skipped_gate',
            reason=f"Unknown strategy '{command}'. Available: {list(STRATEGIES.keys())}",
        )
    strat = STRATEGIES[command]()
    return strat.scan()


def format_result(r: ScanResult) -> str:
    """Format scan result for terminal display."""
    lines = []
    lines.append(f"=== {r.strategy} @ {r.timestamp_et} ET ===")
    if r.regime:
        lines.append(f"Regime: {r.regime}")
    lines.append(f"Status: {r.status} — {r.reason}")
    if r.picks:
        lines.append("")
        lines.append(f"{'#':>2s} {'Sym':6s} {'Entry':>8s} {'SL':>18s} {'TP':>18s} {'Trail':>7s} {'Reason'}")
        for i, p in enumerate(r.picks, 1):
            sl_str = f"${p.sl_price:.2f} ({p.extra.get('sl_pct',0):+.1f}%)" if p.extra.get('sl_pct') else f"${p.sl_price:.2f}"
            tp_str = f"${p.tp_price:.2f} (+{p.extra.get('tp_pct',0):.1f}%)" if p.tp_price and p.extra.get('tp_pct') else f"${p.tp_price:.2f}" if p.tp_price else "-"
            trail_str = f"{p.trail_pct}%" if p.trail_pct else "-"
            lines.append(
                f"{i:>2d} {p.symbol:6s} ${p.entry:>7.2f} {sl_str:>18s} {tp_str:>18s} {trail_str:>7s}"
            )
            lines.append(f"     {p.reason}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'auto'
    if cmd == 'list':
        for s in list_strategies():
            print(f"{s['name']:20s} {s['time_window']:18s} WR {s['expected_wr']*100:.0f}% EV +{s['expected_ev']*100:.2f}%  — {s['description']}")
    else:
        result = run_scan(cmd)
        print(format_result(result))
