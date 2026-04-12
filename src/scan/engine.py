"""
Scan engine — dispatches `scan` commands to the right strategy.

Usage:
    from src.scan.engine import run_scan
    result = run_scan('ml_filter')
    result = run_scan('auto')  # auto-select by time/regime

Command routing:
    scan ml_filter  → MLFilterStrategy
    scan auto       → best strategy for current ET + regime
    scan list       → show available strategies
"""
from datetime import datetime
import pytz

from .strategies.base import ScanResult
from .strategies.orb_prep import OrbPrepStrategy
from .strategies.orb_gap_preview import OrbGapPreviewStrategy
from .strategies.orb_gap_break import OrbGapBreakStrategy
from .strategies.vwap_reclaim import VwapReclaimStrategy
from .strategies.crisis_reversal import CrisisReversalStrategy
from .strategies.ml_filter import MLFilterStrategy
from .strategies.meta import EodFlattenStrategy

ET = pytz.timezone('US/Eastern')

# Trade strategies (all attempt actual entries; may return no_picks)
TRADE_STRATEGIES = {
    'ml_filter':           MLFilterStrategy,         # PRIORITY — 75%+ WR ensemble
    'orb_gap_break':       OrbGapBreakStrategy,      # 81% WR gap ≥5% at open
    'orb_gap_preview':     OrbGapPreviewStrategy,    # 04:00-09:29 PM gap preview
    'orb_prep':            OrbPrepStrategy,
    'vwap_reclaim':        VwapReclaimStrategy,
    'crisis_reversal':     CrisisReversalStrategy,
}

# Meta strategies (specific windows with no real trade, e.g. MOC)
META_STRATEGIES = {
    'eod_flatten': EodFlattenStrategy,
}

STRATEGIES = {**TRADE_STRATEGIES, **META_STRATEGIES}


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

    Priority order (explicit — backtest-validated WR):
    1. orb_gap_preview  04:00-09:29  (82% WR)
    2. orb_gap_break    09:35-09:40  (81% WR) — beats open_drive
    3. ml_filter        09:30-14:00  (75-90% WR bucketed) — PRIMARY intraday
    4. Other narrow-window strategies by EV (vwap_reclaim, ...)
    5. Meta strategies (eod_flatten)
    6. Wide fallbacks (crisis_reversal)
    """
    now_et = datetime.now(ET).strftime("%H:%M")

    def in_window(name: str) -> bool:
        s = STRATEGIES[name]()
        return s.time_start <= now_et <= s.time_end

    # Explicit priority — these beat EV-sort if in window
    PRIORITY = ['orb_gap_preview', 'orb_gap_break', 'ml_filter']
    for name in PRIORITY:
        if name in TRADE_STRATEGIES and in_window(name):
            return name

    # Remaining narrow-window trade strategies by EV desc
    narrow_trade = []
    wide_trade = []
    for name, cls in TRADE_STRATEGIES.items():
        if name in PRIORITY:
            continue
        s = cls()
        if s.time_start <= now_et <= s.time_end:
            window_min = _window_minutes(s.time_start, s.time_end)
            if window_min <= 180:
                narrow_trade.append((name, s.expected_ev, window_min))
            else:
                wide_trade.append((name, s.expected_ev, window_min))

    if narrow_trade:
        narrow_trade.sort(key=lambda x: (-x[1], x[2]))
        return narrow_trade[0][0]

    # Meta (dead zones)
    for name, cls in META_STRATEGIES.items():
        s = cls()
        if s.time_start <= now_et <= s.time_end:
            return name

    # Wide fallback (crisis_reversal)
    if wide_trade:
        wide_trade.sort(key=lambda x: -x[1])
        return wide_trade[0][0]

    return 'ml_filter'


def _window_minutes(start: str, end: str) -> int:
    """Minutes in a HH:MM-HH:MM window."""
    sh, sm = map(int, start.split(':'))
    eh, em = map(int, end.split(':'))
    return (eh - sh) * 60 + (em - sm)


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
