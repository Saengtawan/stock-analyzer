"""
Meta-strategies — cover time windows where no edge exists.

These strategies explicitly return "no trade" or "manage positions"
with informative context. They exist so that `scan auto` always has
something to dispatch to, and user gets a clear answer rather than
hunting for the right strategy.

Backtest-validated dead zones (2025+ data):
- 09:30-09:50: raw WR ~50%, noisy open — observe only
- 10:45-11:30: fading edge (WR 48-54%, EV near zero)
- 11:30-13:00: lunch hour drag (WR 50-52%, no reliable edge)
- 13:30-14:00: transition (WR 50%)
- 14:00-15:30: late afternoon dead zone (WR ~50%)
- 15:55-16:00: MOC window, flatten intraday positions
"""
from .base import BaseStrategy, ScanResult


class _MetaStrategy(BaseStrategy):
    """Base for meta strategies that always skip with a message."""
    message: str = "No edge in this window"

    def scan(self) -> ScanResult:
        if not self.in_time_window():
            return self.out_of_window()
        return ScanResult(
            strategy=self.name,
            timestamp_et=self.time_et_str(),
            status='skipped_gate',
            reason=self.message,
        )


class OpenObserveStrategy(_MetaStrategy):
    name = "open_observe"
    description = "Opening 20-min observation — too noisy for entry"
    expected_wr = 0.0
    expected_ev = 0.0
    time_start = "09:30"
    time_end = "09:50"
    version = "1.0"
    message = (
        "Observation only (09:30-09:50). Backtest: first 20min is too noisy "
        "(raw WR ~50%). Wait for morning_drive at 09:50 when edge window opens. "
        "Monitor ORB watchlist levels: break above PDH = bullish confirm; "
        "break below PDL = bearish."
    )


class LateMorningQuietStrategy(_MetaStrategy):
    name = "late_morning_quiet"
    description = "Post-morning_drive quiet zone — manage positions only"
    expected_wr = 0.0
    expected_ev = 0.0
    time_start = "10:45"
    time_end = "13:00"
    version = "1.0"
    message = (
        "No-trade zone (10:45-13:00). Backtest: edge fades after 10:45 "
        "(WR 48-54%, EV ~0%). Lunch hour volume drops. "
        "Position management only: trail 1% from peak, honor -1.5% SL. "
        "Wait for afternoon_strict at 13:00 if strict setup appears."
    )


class LateAfternoonQuietStrategy(_MetaStrategy):
    name = "late_afternoon_quiet"
    description = "Late afternoon dead zone — EOD management"
    expected_wr = 0.0
    expected_ev = 0.0
    time_start = "13:30"
    time_end = "15:30"
    version = "1.0"
    message = (
        "No-trade zone (13:30-15:30). Backtest: WR ~50% with no filter rescue "
        "after 14:00. EV near zero. Exit drift zone. "
        "Position management: trail stops, prepare EOD flatten at 15:55. "
        "Wait for ovn_gap at 15:30 if OVN setup qualifies."
    )


class EodFlattenStrategy(_MetaStrategy):
    name = "eod_flatten"
    description = "MOC window — flatten intraday positions"
    expected_wr = 0.0
    expected_ev = 0.0
    time_start = "15:55"
    time_end = "16:00"
    version = "1.0"
    message = (
        "EOD flatten (15:55-16:00). All intraday positions exit at MOC. "
        "Overnight positions (ovn_gap, fri_mon) already entered by now. "
        "No new intraday entries — market about to close. "
        "Review day's P&L, journal trades, prep for tomorrow."
    )
