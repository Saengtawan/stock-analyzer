"""
Unified Brain — one model that sees EVERYTHING.
Replaces: kernel rank + StockBrain + separate filters.
Part of Discovery v12.0.

28 features: 4 technical + 6 interaction + 5 macro + 4 sector + 8 stock + 1 regime
Target: outcome_5d > 0
"""
import logging
import sqlite3
import time
import numpy as np
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'trade_history.db'

SENSOR_FEATURES = [
    'sensor_vix', 'sensor_crude', 'sensor_breadth', 'sensor_yield', 'sensor_spy',
    'sensor_sector_strength', 'sensor_sector_leading', 'sensor_sector_aligned', 'sensor_rotation',
    'sensor_speculative', 'sensor_crude_sens', 'sensor_vix_sens', 'sensor_supply_risk',
    'sensor_analyst', 'sensor_insider', 'sensor_candle', 'sensor_earnings_risk',
]

TECHNICAL_FEATURES = [
    'atr_pct', 'momentum_5d', 'distance_from_20d_high', 'volume_ratio',
    'mom_x_d20h', 'atr_x_d20h', 'vol_x_mom', 'is_deep_dip', 'is_momentum', 'dip_relative_atr',
]


class UnifiedBrain:
    """Single XGBoost model that sees ALL signals."""

    def __init__(self):
        self.model = None
        self._fitted = False
        self._n_train = 0
        self._feature_importance = {}
        self._last_fit_time = 0.0
        self._feature_names = TECHNICAL_FEATURES + SENSOR_FEATURES + ['regime_prob']

    def fit(self, sensor_network=None, max_date: str = None) -> bool:
        """Train on ALL features: technical + sensors."""
        from sklearn.ensemble import GradientBoostingClassifier

        X, y, outcomes = self._load_training_data(sensor_network, max_date)
        if len(X) < 500:
            logger.warning("UnifiedBrain: insufficient data (%d)", len(X))
            return False

        self.model = GradientBoostingClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.03,
            min_samples_leaf=30, subsample=0.8, random_state=42,
        )
        self.model.fit(X, y)

        self._fitted = True
        self._n_train = len(X)
        self._last_fit_time = time.time()
        self._feature_importance = {
            name: round(float(imp), 4)
            for name, imp in zip(self._feature_names, self.model.feature_importances_)
        }

        train_acc = float((self.model.predict(X) == y).mean()) * 100
        logger.info("UnifiedBrain: fitted %d signals, acc=%.1f%%, top: %s",
                     len(X), train_acc,
                     ', '.join(f'{k}={v:.3f}' for k, v in
                               sorted(self._feature_importance.items(), key=lambda x: -x[1])[:5]))
        return True

    def predict(self, technical: dict, sensors: dict, regime_prob: float = 0.5) -> dict:
        """Predict win probability from ALL signals."""
        if not self._fitted or self.model is None:
            return {'probability': 0.49, 'confidence': 0}

        x = self._build_vector(technical, sensors, regime_prob)
        prob = float(self.model.predict_proba(x.reshape(1, -1))[0, 1])

        return {
            'probability': round(prob, 4),
            'predicted_class': 1 if prob >= 0.5 else 0,
            'confidence': round(abs(prob - 0.5) * 200, 1),
        }

    def needs_refit(self, days: int = 30) -> bool:
        if not self._fitted:
            return True
        return (time.time() - self._last_fit_time) > days * 86400

    def get_stats(self) -> dict:
        return {
            'fitted': self._fitted,
            'n_train': self._n_train,
            'n_features': len(self._feature_names),
            'feature_importance': self._feature_importance,
        }

    def _build_vector(self, technical: dict, sensors: dict, regime_prob: float) -> np.ndarray:
        """Build feature vector from technical + sensors + regime."""
        # Technical (10)
        atr = float(technical.get('atr_pct') or 3)
        mom = float(technical.get('momentum_5d') or 0)
        d20h = float(technical.get('distance_from_20d_high') or -5)
        vol = float(technical.get('volume_ratio') or 1)

        tech = [
            atr, mom, d20h, vol,
            mom * d20h / 100, atr * abs(d20h) / 100,
            vol * abs(mom) / 10,
            1.0 if mom < -5 and d20h < -15 else 0.0,
            1.0 if mom > 3 and d20h > -5 else 0.0,
            abs(d20h) / max(atr, 0.5),
        ]

        # Sensors (17)
        sens = [float(sensors.get(f, 0)) for f in SENSOR_FEATURES]

        # Regime (1)
        regime = [float(regime_prob)]

        return np.array(tech + sens + regime, dtype=np.float64)

    def _load_training_data(self, sensor_network, max_date: str = None):
        """Load historical data with sensor signals computed."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            date_filter = f"AND b.scan_date <= '{max_date}'" if max_date else ""
            rows = conn.execute(f"""
                SELECT b.scan_date, b.symbol, b.atr_pct, b.momentum_5d,
                       b.distance_from_20d_high, b.volume_ratio, b.sector,
                       b.outcome_5d,
                       COALESCE(m.vix_close, 20), m.crude_close, m.yield_10y,
                       mb.pct_above_20d_ma, mb.new_52w_lows
                FROM backfill_signal_outcomes b
                LEFT JOIN macro_snapshots m ON b.scan_date = m.date
                LEFT JOIN market_breadth mb ON b.scan_date = mb.date
                WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0
                AND m.vix_close IS NOT NULL
                {date_filter}
                ORDER BY b.scan_date
            """).fetchall()

            # Load context data
            spec_flags = {}
            crude_sens = {}
            analyst_data = {}
            for r in conn.execute("SELECT symbol, context_type, score FROM stock_context").fetchall():
                if r[1] == 'SPECULATIVE_FLAG':
                    spec_flags[r[0]] = r[2]
                elif r[1] == 'CRUDE_SENSITIVE':
                    crude_sens[r[0]] = r[2]
            for r in conn.execute("SELECT symbol, upside_pct FROM analyst_consensus").fetchall():
                if r[1] is not None:
                    analyst_data[r[0]] = min(1, max(-1, r[1] / 30))

            # Sector ranks per date
            sector_rows = conn.execute("""
                SELECT date, sector, SUM(pct_change) as ret
                FROM sector_etf_daily_returns
                WHERE sector NOT IN ('S&P 500','US Dollar','Treasury Long','Gold')
                GROUP BY date, sector
            """).fetchall()
        finally:
            conn.close()

        # Build sector rank lookup
        sector_by_date = defaultdict(dict)
        for r in sector_rows:
            sector_by_date[r[0]][r[1]] = r[2] or 0

        X, y_labels, outcomes = [], [], []
        for r in rows:
            atr = float(r[2])
            mom = float(r[3] or 0)
            d20h = float(r[4] or -5)
            vol = float(r[5] or 1)
            sector = r[6] or ''
            outcome = float(r[7])
            vix = float(r[8])
            crude = float(r[9] or 75)
            y10 = float(r[10] or 4)
            breadth = float(r[11] or 50)

            # Technical (10)
            tech = [
                atr, mom, d20h, vol,
                mom * d20h / 100, atr * abs(d20h) / 100,
                vol * abs(mom) / 10,
                1.0 if mom < -5 and d20h < -15 else 0.0,
                1.0 if mom > 3 and d20h > -5 else 0.0,
                abs(d20h) / max(atr, 0.5),
            ]

            # Simplified sensors (from available data)
            vix_state = min(1, max(-1, (vix - 20) / 15))
            crude_state = min(1, max(-1, (crude - 75) / 25))
            breadth_state = min(1, max(-1, (breadth - 50) / 30))
            yield_state = min(1, max(-1, (y10 - 3.5) / 1.5))
            spy_state = 0  # can't compute easily here

            # Sector
            sr = sector_by_date.get(r[0], {})
            sorted_sectors = sorted(sr.items(), key=lambda x: -x[1])
            sector_rank = next((i + 1 for i, (s, _) in enumerate(sorted_sectors) if s == sector), 6)
            sector_strength = 1 - (sector_rank - 1) / 10

            rules = SENSOR_MACRO_RULES.get(sector, {})
            alignment = 0
            if rules.get('crude') == 'pos' and crude > 85:
                alignment += 0.3
            elif rules.get('crude') == 'neg' and crude > 85:
                alignment -= 0.3
            if rules.get('vix') == 'pos' and vix > 25:
                alignment += 0.3
            elif rules.get('vix') == 'neg' and vix > 25:
                alignment -= 0.3

            sensors = [
                vix_state, crude_state, breadth_state, yield_state, spy_state,
                sector_strength, 1.0 if sector_rank <= 3 else 0.0,
                min(1, max(-1, alignment)), 0,  # rotation=0 (simplified)
                spec_flags.get(r[1], 0),
                crude_sens.get(r[1], 0), 0,  # vix_sens=0 (limited data)
                0,  # supply_risk (simplified)
                analyst_data.get(r[1], 0), 0, 0, 0,  # insider, candle, earnings (simplified)
            ]

            regime = [0.5]  # neutral (can't compute historical regime prob easily)

            X.append(tech + sensors + regime)
            y_labels.append(1 if outcome > 0 else 0)
            outcomes.append(outcome)

        return (np.array(X, dtype=np.float64),
                np.array(y_labels, dtype=np.int32),
                np.array(outcomes, dtype=np.float64))


# Simplified sector-macro rules for training
SENSOR_MACRO_RULES = {
    'Energy': {'crude': 'pos', 'vix': 'neu'},
    'Financial Services': {'crude': 'neu', 'vix': 'neu'},
    'Technology': {'crude': 'neg', 'vix': 'neg'},
    'Consumer Cyclical': {'crude': 'neg', 'vix': 'neg'},
    'Utilities': {'crude': 'neu', 'vix': 'pos'},
    'Consumer Defensive': {'crude': 'neu', 'vix': 'pos'},
    'Healthcare': {'crude': 'neu', 'vix': 'neu'},
    'Industrials': {'crude': 'neg', 'vix': 'neg'},
    'Real Estate': {'crude': 'neu', 'vix': 'neg'},
    'Basic Materials': {'crude': 'neu', 'vix': 'neg'},
    'Communication Services': {'crude': 'neu', 'vix': 'neg'},
}
