"""
Risk Brain — Portfolio-level risk management rules.
Part of Discovery AI v7.0 Multi-Brain Council.

Rule-based (not ML): sector limits, exposure caps, loss streaks.
"""
import logging
import sqlite3
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'


class RiskBrain:
    """Portfolio-level risk gating for discovery picks."""

    def __init__(self, max_per_sector: int = 3, max_positions: int = 5,
                 max_consecutive_losses: int = 3, max_daily_loss_pct: float = 3.0,
                 capital: float = 5000):
        self.max_per_sector = max_per_sector
        self.max_positions = max_positions
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_loss_pct = max_daily_loss_pct
        self.capital = capital

    def evaluate(self, picks: list, active_positions: list = None) -> list:
        """Evaluate risk for each pick and assign action.

        Args:
            picks: list of pick dicts (symbol, sector, sl_pct, tp1_pct, ...)
            active_positions: list of currently open position dicts

        Returns:
            list of dicts with risk_action (ALLOW/REDUCE_SIZE/BLOCK) and reasons
        """
        active_positions = active_positions or []
        active_sectors = Counter(p.get('sector', '') for p in active_positions)
        active_symbols = {p.get('symbol', '') for p in active_positions}
        n_active = len(active_positions)

        # Check recent loss streak
        consecutive_losses = self._get_consecutive_losses()

        results = []
        new_sectors = Counter()

        for pick in picks:
            symbol = pick.get('symbol', '')
            sector = pick.get('sector', '')
            sl_pct = pick.get('sl_pct', 3.0) or 3.0

            action = 'ALLOW'
            size_mult = 1.0
            reasons = []

            # Rule 1: No duplicate positions
            if symbol in active_symbols:
                action = 'BLOCK'
                reasons.append(f'Already have {symbol}')

            # Rule 2: Sector concentration
            total_sector = active_sectors.get(sector, 0) + new_sectors.get(sector, 0)
            if total_sector >= self.max_per_sector:
                action = 'BLOCK'
                reasons.append(f'Sector {sector} full ({total_sector}/{self.max_per_sector})')

            # Rule 3: Max total positions
            total_pos = n_active + len([r for r in results if r['risk_action'] in ('ALLOW', 'REDUCE_SIZE')])
            if total_pos >= self.max_positions:
                action = 'BLOCK'
                reasons.append(f'Max positions ({self.max_positions})')

            # Rule 4: Consecutive losses → reduce
            if consecutive_losses >= self.max_consecutive_losses and action == 'ALLOW':
                action = 'REDUCE_SIZE'
                size_mult = 0.5
                reasons.append(f'{consecutive_losses} consecutive losses → half size')

            # Rule 5: Max daily potential loss
            # Each position is capital/max_positions, not full capital
            if action == 'ALLOW':
                pos_size = self.capital / self.max_positions
                existing_risk = sum(p.get('sl_pct', 3) * pos_size / 100 for p in active_positions)
                new_risk = sl_pct * pos_size / 100
                total_risk = existing_risk + new_risk
                max_allowed = self.capital * self.max_daily_loss_pct / 100
                if total_risk > max_allowed:
                    action = 'REDUCE_SIZE'
                    safe_risk = max(0, max_allowed - existing_risk)
                    size_mult = max(0.25, safe_risk / new_risk) if new_risk > 0 else 0.25
                    reasons.append(f'Risk ${total_risk:.0f} > max ${max_allowed:.0f}')

            if not reasons:
                reasons.append('All checks passed')

            result = {
                'symbol': symbol,
                'risk_action': action,
                'size_multiplier': round(size_mult, 2),
                'reasons': reasons,
                'sector_count': total_sector,
                'total_positions': total_pos,
                'consecutive_losses': consecutive_losses,
            }
            results.append(result)

            # Count ALLOW and REDUCE_SIZE toward limits (both result in trades)
            if action in ('ALLOW', 'REDUCE_SIZE'):
                new_sectors[sector] += 1

        return results

    def _get_consecutive_losses(self) -> int:
        """Count consecutive losses from recent discovery outcomes."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            rows = conn.execute("""
                SELECT actual_return_d3 FROM discovery_outcomes
                WHERE actual_return_d3 IS NOT NULL
                ORDER BY scan_date DESC, symbol DESC
                LIMIT 20
            """).fetchall()
            conn.close()

            count = 0
            for r in rows:
                if r[0] < 0:  # breakeven (0%) is NOT a loss
                    count += 1
                else:
                    break
            return count
        except Exception:
            return 0

    def get_stats(self) -> dict:
        return {
            'max_per_sector': self.max_per_sector,
            'max_positions': self.max_positions,
            'max_consecutive_losses': self.max_consecutive_losses,
            'consecutive_losses': self._get_consecutive_losses(),
        }
