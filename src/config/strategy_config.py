"""
Strategy Configuration - Single Source of Truth

v2.0 - FULL MIGRATION (v6.10):
- Consolidates ALL 159 parameters from trading.yaml
- Complete type-safe configuration
- Supports YAML and dict loading
- Hot-reload without restart
- Zero hardcoded constants in components

v1.0 - UNIFIED CONFIGURATION:
- Consolidates 70+ constants from 4 components
- Type-safe dataclass with validation
- Supports YAML and dict loading
- Hot-reload without restart

Usage:
    # From YAML
    config = RapidRotationConfig.from_yaml('config/trading.yaml')

    # From dict
    config = RapidRotationConfig.from_dict({'min_sl_pct': 2.5})

    # Default values
    config = RapidRotationConfig()

    # Use in components
    screener = RapidRotationScreener(config=config)
    portfolio = RapidPortfolioManager(config=config)
    engine = AutoTradingEngine(config=config)
"""
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
import yaml
from pathlib import Path


@dataclass
class SessionConfig:
    """Trading session configuration"""
    start: int          # Start time in minutes from midnight
    end: int            # End time in minutes from midnight
    interval: int       # Scan interval in minutes (0 = no continuous scan)
    label: str          # Display label

    @classmethod
    def from_dict(cls, data: dict) -> 'SessionConfig':
        return cls(**data)


@dataclass
class RapidRotationConfig:
    """
    Unified configuration for Rapid Rotation Strategy

    Single source of truth for ALL strategy parameters.
    Replaces 159 scattered constants across components.

    v2.0: Full migration - all YAML params consolidated
    v1.0: Initial unified config - 43 core params
    """

    # =========================================================================
    # STOP LOSS / TAKE PROFIT (v6.10: Unified from 3 sources)
    # =========================================================================
    # ATR-based SL/TP (primary method)
    atr_sl_multiplier: float = 1.5      # SL = 1.5 × ATR
    atr_tp_multiplier: float = 3.0      # TP = 3 × ATR

    # Safety caps (prevent extreme values)
    min_sl_pct: float = 2.0             # Minimum SL% (tightest allowed)
    max_sl_pct: float = 3.0             # Maximum SL% (widest allowed - user requested)
    min_tp_pct: float = 4.0             # Minimum TP% (shortest allowed)
    max_tp_pct: float = 8.0             # Maximum TP% (longest allowed)

    # Fallback percentages (when ATR unavailable)
    default_sl_pct: float = 2.5         # Default SL if ATR fails
    default_tp_pct: float = 5.0         # Default TP if ATR fails

    # PDT-specific threshold
    pdt_tp_threshold: float = 4.0       # PDT take-profit threshold

    # =========================================================================
    # TRAILING STOP
    # =========================================================================
    trail_enabled: bool = True          # Enable trailing stop
    trail_activation_pct: float = 3.0   # Activate trailing at +3% gain
    trail_lock_pct: float = 75.0        # Lock 75% of peak gains (legacy: 75)

    # =========================================================================
    # POSITION MANAGEMENT
    # =========================================================================
    max_positions: int = 3              # Max concurrent positions (legacy)
    max_positions_total: int = 5        # v6.53: Global limit (2 DIP + 1 OVN + 1 PEM + 1 PED = 5 max)
    max_hold_days: int = 10             # Max days to hold (time stop, legacy: 10)
    position_size_pct: float = 40.0     # Position size (% of equity, legacy)
    max_position_pct: float = 50.0      # Max position size (% of equity, legacy: 50)
    simulated_capital: Optional[int] = 4000  # Simulated capital (null = use real account)
    risk_parity_enabled: bool = True    # Enable risk-parity sizing
    risk_budget_pct: float = 1.0        # Max risk per position (% of account)

    # =========================================================================
    # SCORING & FILTERING
    # =========================================================================
    min_score: int = 90                 # Minimum score to qualify (legacy: 90)
    min_atr_pct: float = 2.5            # Minimum volatility (ATR%)
    max_rsi_entry: int = 65             # Block RSI > 65 (20% WR)
    avoid_mom_range: List[int] = field(default_factory=lambda: [10, 12])  # Skip momentum 10-12%

    # v6.20: Momentum 5d Filter (dip-bounce strategy requirement)
    momentum_5d_min_dip: float = -1.0   # Must have dipped at least -1.0% (block shallow dips)
    momentum_5d_max_dip: float = -15.0  # Max dip allowed -15% (block crashed stocks)

    # =========================================================================
    # REGIME FILTERING
    # =========================================================================
    regime_filter_enabled: bool = True  # Enable SPY regime filter
    regime_sma_period: int = 20         # SMA period for regime check
    regime_rsi_min: int = 40            # Min RSI for regime
    regime_return_5d_min: float = -2.0  # Min 5-day return for regime
    regime_vix_max: float = 30.0        # Max VIX (critical for BEAR survival)
    vix_skip_zone_enabled: bool = True  # Block buys in VIX 20-24 (uncertainty zone)
    vix_skip_zone_low: float = 20.0     # VIX skip zone lower bound
    vix_skip_zone_high: float = 24.0    # VIX skip zone upper bound
    opening_window_limit_enabled: bool = True  # Stagger buys during first 30 min of market open
    opening_window_minutes: int = 30    # Duration of opening window
    opening_window_stagger_minutes: int = 15   # v6.35: Minutes to wait between buys in opening window
    skip_before_holiday: bool = True    # Skip new positions before holidays

    # =========================================================================
    # SECTOR SCORING
    # =========================================================================
    sector_bull_threshold: float = 3.0  # > +3% = BULL sector
    sector_bear_threshold: float = -3.0 # < -3% = BEAR sector
    sector_bull_bonus: int = 0          # Bonus points for BULL sector (disabled)
    sector_bear_penalty: int = 0        # Penalty for BEAR sector (disabled)
    sector_sideways_adj: int = 0        # Adjustment for SIDEWAYS sector

    # =========================================================================
    # DYNAMIC SECTOR REFRESH (v6.20 Refactor #2)
    # =========================================================================
    sector_vix_threshold: float = 20.0      # VIX > 20 = volatile market
    sector_ttl_volatile_min: int = 2        # Sector refresh TTL when volatile (minutes)
    sector_ttl_normal_min: int = 5          # Sector refresh TTL when normal (minutes)
    sector_vix_cache_ttl_sec: int = 60      # Cache VIX for N seconds (balance freshness vs API calls)

    # =========================================================================
    # SECTOR DIVERSIFICATION
    # =========================================================================
    sector_filter_enabled: bool = True  # Enable sector filter
    max_per_sector: int = 2             # Max positions per sector
    sector_loss_tracking_enabled: bool = True  # Track sector losses
    max_sector_consecutive_loss: int = 2       # Max consecutive losses per sector
    sector_cooldown_days: int = 2       # Cooldown days after sector losses

    # Dynamic Sector Gate (VIX-based quota)
    dynamic_sector_gate_enabled: bool = True  # Adjust max_per_sector by VIX tier
    sector_gate_normal_max: int = 2   # VIX < 20 (NORMAL)
    sector_gate_skip_max: int = 1     # VIX 20-24 (SKIP)
    sector_gate_high_max: int = 1     # VIX 24-38 (HIGH)
    sector_gate_extreme_max: int = 0  # VIX > 38 (EXTREME)

    # =========================================================================
    # BULL SECTOR FILTER
    # =========================================================================
    bull_sector_filter_enabled: bool = True  # Enable BULL sector filter
    bull_sector_min_return: int = -3    # Absolute: block if return_20d < -3% (sector BEAR)
    sector_weak_relative_n: int = 2     # Relative: also block bottom N sectors by 20d return (0=disable)

    # =========================================================================
    # ALTERNATIVE DATA
    # =========================================================================
    alt_data_max_bonus: int = 15        # Max bonus from alt data
    alt_data_max_penalty: int = -15     # Max penalty from alt data

    # =========================================================================
    # SAFETY & RISK MANAGEMENT
    # =========================================================================
    daily_loss_limit_pct: float = 3.0   # Daily loss limit (% of equity, legacy: 3.0)
    weekly_loss_limit_pct: float = 7.0  # Weekly loss limit (% of equity)
    min_buying_power_pct: float = 10.0  # Min buying power to keep (%)

    # PDT (Pattern Day Trader) settings
    pdt_account_threshold: float = 25000.0  # PDT threshold ($)
    pdt_day_trade_limit: int = 3            # Max day trades (non-PDT)
    pdt_reserve: int = 1                    # Keep N day trades for emergencies (v6.10.1)
    pdt_enforce_always: bool = True         # Always enforce PDT rules

    # SPY Intraday Filter (blocks new entries when SPY already selling off)
    spy_intraday_filter_enabled: bool = True
    spy_intraday_filter_pct: float = -1.0   # Block if SPY down >1% from today's open

    # VIX Spike Protection (tighten SLs when VIX jumps sharply)
    vix_spike_protection_enabled: bool = True
    vix_spike_pct: float = 15.0             # Trigger if VIX up >15% vs yesterday close
    vix_spike_sl_tighten_pct: float = 1.0  # Tighten SL to N% below current price

    # Circuit breaker
    max_consecutive_losses: int = 3     # Circuit breaker trigger (legacy: 3)
    circuit_breaker_pause_hours: int = 1 # Pause duration after breaker
    circuit_breaker_max_errors: int = 5  # Max errors before circuit breaker

    # Slippage tracking
    max_slippage_pct: float = 0.5       # Max acceptable slippage (%)

    # =========================================================================
    # SIGNAL QUEUE (v4.1)
    # =========================================================================
    queue_enabled: bool = True          # Enable signal queue
    queue_atr_mult: float = 0.5         # ATR multiplier for queue entry
    queue_min_deviation: float = 0.5    # Min price deviation (%)
    queue_max_deviation: float = 1.5    # Max price deviation (%)
    queue_max_size: int = 3             # Max queue size
    queue_freshness_window: int = 30    # Freshness window (minutes)
    queue_rescan_on_empty: bool = True  # Rescan when queue empty

    # =========================================================================
    # SMART ORDER (v4.8)
    # =========================================================================
    smart_order_enabled: bool = True    # Enable smart order execution
    smart_order_max_spread_pct: float = 1.0  # Max bid-ask spread (%)
    smart_order_wait_seconds: int = 30  # Wait time for better price (seconds)

    # =========================================================================
    # GAP FILTER (v4.3)
    # =========================================================================
    gap_filter_enabled: bool = True     # Enable gap filter
    gap_max_up: float = 2.0             # Max gap up (%)
    gap_max_down: float = -5.0          # Max gap down (%)

    # =========================================================================
    # EARNINGS FILTER (v4.4)
    # =========================================================================
    earnings_filter_enabled: bool = True        # Enable earnings filter
    earnings_skip_days_before: int = 5          # Skip days before earnings
    earnings_skip_days_after: int = 0           # Skip days after earnings
    earnings_no_data_action: str = "warn"       # Action when no data: allow, skip, warn
    earnings_auto_sell: bool = True             # Auto-sell before earnings
    earnings_auto_sell_buffer_min: int = 30     # Minutes before close to auto-sell

    # =========================================================================
    # LOW RISK MODE (v4.5)
    # =========================================================================
    low_risk_mode_enabled: bool = True  # Enable low risk mode
    low_risk_gap_max_up: float = 1.0    # Gap filter for low risk mode (%)
    low_risk_min_score: int = 90        # Min score for low risk mode
    low_risk_position_size_pct: int = 20  # Position size for low risk (%)
    low_risk_max_atr_pct: float = 4.0   # Max ATR for low risk mode (%)

    # =========================================================================
    # AFTERNOON SCAN (v4.9.1)
    # =========================================================================
    afternoon_scan_enabled: bool = True     # Enable afternoon scan
    afternoon_scan_hour: int = 14           # Afternoon scan hour (ET)
    afternoon_scan_minute: int = 0          # Afternoon scan minute
    afternoon_min_score: int = 87           # Min score for afternoon (stricter)
    afternoon_gap_max_up: float = 1.5       # Afternoon gap max up (tighter)
    afternoon_gap_max_down: float = -3.0    # Afternoon gap max down (tighter)

    # =========================================================================
    # PRE-FILTER AUTO-REFRESH (v6.18)
    # =========================================================================
    pre_filter_on_demand_enabled: bool = True       # Enable auto-refresh
    pre_filter_on_demand_min_pool: int = 200        # Refresh if pool < 200
    pre_filter_on_demand_zero_signals: int = 3      # Refresh if 0 signals × N scans
    pre_filter_intraday_enabled: bool = True        # Enable scheduled refresh
    pre_filter_intraday_schedule: list = None       # Hours to refresh [10, 13, 15]
    pre_filter_intraday_minute: int = 45            # Minute of each scheduled hour (e.g. 10:45, 13:45, 15:45)
    pre_filter_max_per_day: int = 6                 # Max refreshes per day

    # =========================================================================
    # MARKET HOURS (v6.4 Single Source of Truth)
    # =========================================================================
    market_open_hour: int = 9           # Market open hour (ET)
    market_open_minute: int = 30        # Market open minute
    market_close_hour: int = 16         # Market close hour (ET)
    market_close_minute: int = 0        # Market close minute
    pre_close_minute: int = 50          # Pre-close check (15:50 ET)
    market_open_minutes: int = 570      # 09:30 ET = 9*60+30
    market_close_minutes: int = 960     # 16:00 ET = 16*60

    # v6.36: Skip Window (no trading period to avoid volatile mid-morning)
    skip_window_enabled: bool = True    # Enable skip window
    skip_window_start_hour: int = 10    # Skip window start hour (ET)
    skip_window_start_minute: int = 0   # Skip window start minute
    skip_window_end_hour: int = 11      # Skip window end hour (ET)
    skip_window_end_minute: int = 0     # Skip window end minute

    # =========================================================================
    # SESSION TIMELINE (v6.4 Single Source of Truth)
    # =========================================================================
    # UI timeline bar uses these values. All times in minutes from midnight.
    sessions: Dict[str, SessionConfig] = field(default_factory=lambda: {
        'morning': SessionConfig(start=575, end=660, interval=3, label='Morning'),
        'midday': SessionConfig(start=660, end=840, interval=5, label='Midday'),
        'afternoon': SessionConfig(start=840, end=930, interval=5, label='Afternoon'),
        'preclose': SessionConfig(start=930, end=960, interval=0, label='Pre-Close')
    })

    # =========================================================================
    # CONTINUOUS SCAN (v6.3)
    # =========================================================================
    continuous_scan_enabled: bool = True            # Enable continuous scan
    continuous_scan_interval_minutes: int = 5       # Default/slow interval (11:00-16:00)
    continuous_scan_volatile_interval: int = 3      # Volatile period interval (09:35-11:00)
    continuous_scan_volatile_end_hour: int = 11     # Volatile period ends at 11:00
    continuous_scan_midday_hour: int = 12           # Switch to afternoon params after this hour

    # =========================================================================
    # LATE START PROTECTION (v4.4)
    # =========================================================================
    late_start_protection: bool = True      # Enable late start protection
    market_open_scan_delay: int = 5         # Minutes after open before scanning
    market_open_scan_window: int = 20       # Minutes - skip scan if started after this

    # =========================================================================
    # MONITOR INTERVAL
    # =========================================================================
    monitor_interval_seconds: int = 15      # Position monitoring interval (seconds)

    # =========================================================================
    # BEAR MODE PARAMS (v4.9.4)
    # =========================================================================
    bear_mode_enabled: bool = True          # Enable BEAR mode
    bear_max_positions: int = 2             # Max positions in BEAR mode
    bear_min_score: int = 85                # Min score in BEAR mode (relaxed)
    bear_gap_max_up: float = 1.5            # BEAR gap max up (relaxed)
    bear_gap_max_down: float = -3.0         # BEAR gap max down (relaxed)
    bear_position_size_pct: int = 25        # BEAR position size (%)
    bear_max_atr_pct: float = 4.0           # BEAR max ATR (relaxed)

    # =========================================================================
    # QUANT RESEARCH FINDINGS (v5.3)
    # =========================================================================
    stock_d_filter_enabled: bool = True     # Require dip-bounce pattern
    bear_dd_control_exempt: bool = True     # Don't apply DD controls in BEAR

    # =========================================================================
    # CONVICTION-BASED SIZING (v4.9.4)
    # =========================================================================
    conviction_sizing_enabled: bool = True  # Enable conviction-based sizing
    conviction_a_plus_pct: int = 45         # STRONG BULL + insider + score 85+
    conviction_a_pct: int = 40              # BULL + score 80+
    conviction_b_pct: int = 30              # SIDEWAYS + score 80+

    # =========================================================================
    # SMART DAY TRADE (v4.9.4)
    # =========================================================================
    smart_day_trade_enabled: bool = True        # Enable smart day trade
    day_trade_gap_threshold: float = 3.0        # % gap up at open to trigger day trade sell
    day_trade_momentum_threshold: float = 4.0   # % intraday gain to trigger
    day_trade_emergency_enabled: bool = True    # Use day trade for emergency SL

    # =========================================================================
    # OVERNIGHT GAP SCANNER (v4.9.4)
    # =========================================================================
    overnight_gap_enabled: bool = True          # Enable overnight gap scanner
    overnight_gap_scan_hour: int = 15           # Scan hour (ET)
    overnight_gap_scan_minute: int = 30         # Scan minute
    overnight_gap_min_score: int = 70           # Min score for overnight
    overnight_gap_position_pct: int = 35        # Position size (%)
    overnight_gap_target_pct: float = 3.0       # Target profit (%)
    overnight_gap_sl_pct: float = 1.5           # Stop loss (%)
    # v6.31: Adaptive allocation parameters
    overnight_gap_max_pct_of_capital: float = 70.0  # Max % of total capital for overnight
    overnight_gap_min_cash: float = 500.0       # Min cash required to enter overnight position
    overnight_gap_max_positions: int = 1        # Max overnight positions at once

    # =========================================================================
    # BREAKOUT SCANNER (v4.9.4)
    # =========================================================================
    breakout_scan_enabled: bool = True          # Enable breakout scanner
    breakout_min_volume_mult: float = 1.5       # Min volume multiplier
    breakout_min_score: int = 75                # Min score for breakout
    breakout_target_pct: float = 8.0            # Target profit (%)
    breakout_sl_pct: float = 3.0                # Stop loss (%)

    # =========================================================================
    # POST-EARNINGS MOMENTUM (PEM) STRATEGY (v6.29)
    # =========================================================================
    pem_enabled: bool = False                   # Disabled by default (paper trade first)
    pem_gap_threshold_pct: float = 8.0          # Minimum gap up % to qualify
    pem_volume_early_ratio_min: float = 0.15    # Early-session vol ratio vs 20d avg
    pem_scan_hour: int = 9                      # Scan hour (ET)
    pem_scan_minute: int = 35                   # Scan minute (9:35 = after open)
    pem_max_positions: int = 1                  # Max PEM positions at once
    pem_position_size_pct: float = 33.0         # Position size (% of equity)
    pem_sl_pct: float = 5.0                     # Stop loss % (wider for earnings day)

    # =========================================================================
    # PRE-EARNINGS DRIFT (PED) STRATEGY (v6.53)
    # =========================================================================
    ped_enabled: bool = False                   # Disabled by default
    ped_scan_hour: int = 9                      # Scan hour (ET)
    ped_scan_minute: int = 35                   # Scan minute (9:35 = after open)
    ped_max_positions: int = 1                  # Dedicated slot (not counted in DIP limit)
    ped_position_size_pct: float = 30.0         # Position size (% of equity)
    ped_days_before_min: int = 4                # Buy at D-4 (4 trading days before earnings)
    ped_days_before_max: int = 5                # Also allow D-5
    ped_rsi_min: float = 35.0                   # Avoid oversold
    ped_rsi_max: float = 65.0                   # Avoid overbought
    ped_volume_ratio_min: float = 0.8           # Normal volume (no unusual selling)
    ped_max_slippage_pct: float = 1.5           # v6.55: Cancel if live price < signal price by >1.5%

    # =========================================================================
    # VIX ADAPTIVE STRATEGY v3.0 (2026-02-11)
    # =========================================================================
    vix_adaptive_enabled: bool = True           # Enable VIX Adaptive Strategy

    # =========================================================================
    # PRE-FILTER SYSTEM (v6.2)
    # =========================================================================
    pre_filter_enabled: bool = True             # Enable pre-filter system
    pre_filter_min_price: float = 5.0           # Minimum stock price
    pre_filter_min_volume: int = 500000         # Minimum average volume (fallback)
    pre_filter_min_atr_pct: float = 3.0         # Minimum ATR% (increased from 2.5)
    pre_filter_max_overextended: float = 10.0   # Max % above SMA20
    pre_filter_pool_stale_hours: int = 12       # Hours before pool considered stale
    pre_filter_max_rsi: int = 65                # Filter overbought (RSI > 65 = 20% WR)
    pre_filter_min_dollar_volume: int = 5000000 # $5M avg dollar volume (liquidity)
    pre_filter_min_dip_5d: float = 99.0         # Disabled (screener handles dip detection)
    pre_filter_max_dip_5d: float = -15.0        # But not crashed > 15% (safety)

    # =========================================================================
    # BETA/VOLATILITY FILTER (v6.32 - Test Mode)
    # =========================================================================
    beta_filter_enabled: bool = True            # Enable beta/volatility filter
    beta_filter_log_only: bool = True           # TEST MODE: Log only, don't reject
    beta_filter_min_beta: float = 0.5           # Minimum beta for entry
    beta_filter_min_atr_pct: float = 3.0        # Minimum ATR% for entry (lowered from 5.0)
    beta_filter_bypass_core: bool = True        # Bypass check for CORE_STOCKS

    # =========================================================================
    # CACHE SETTINGS
    # =========================================================================
    sector_cache_ttl_days: int = 3      # Sector cache TTL (days)
    price_cache_ttl_seconds: int = 300  # Price cache TTL (seconds)

    # =========================================================================
    # ENTRY PROTECTION (v6.17) - 3-Layer Entry Protection System
    # =========================================================================
    # Prevents buying at opening spike highs
    entry_protection_enabled: bool = True               # Master switch
    entry_block_minutes_after_open: int = 15            # Layer 1: Block first N min
    entry_allow_discount_exception: bool = True         # Allow if price drops
    entry_discount_exception_pct: float = -0.5          # Exception threshold
    entry_vwap_max_distance_pct: float = 1.5            # Layer 2: Max VWAP distance
    entry_vwap_allow_below: bool = True                 # Always allow if below VWAP
    entry_limit_order_only: bool = True                 # Layer 3: Use limits only
    entry_max_chase_pct: float = 0.2                    # Max chase above signal
    entry_limit_timeout_minutes: int = 5                # Limit order timeout
    entry_track_rejections: bool = True                 # Track statistics

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    @classmethod
    def from_yaml(cls, path: str) -> 'RapidRotationConfig':
        """
        Load configuration from YAML file

        Args:
            path: Path to YAML config file

        Returns:
            RapidRotationConfig instance

        Example:
            config = RapidRotationConfig.from_yaml('config/trading.yaml')
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        # Extract rapid_rotation section if exists
        if 'rapid_rotation' in data:
            rapid_rotation_data = data['rapid_rotation']
        else:
            rapid_rotation_data = {}

        # Merge with root-level params (legacy support)
        merged_data = {k: v for k, v in data.items() if k not in ['rapid_rotation', 'sessions']}
        merged_data.update(rapid_rotation_data)

        # v6.10: All parameter names now use consistent new naming (no legacy mapping needed)

        # Handle sessions separately
        if 'sessions' in data:
            sessions_dict = {}
            for session_name, session_data in data['sessions'].items():
                sessions_dict[session_name] = SessionConfig.from_dict(session_data)
            merged_data['sessions'] = sessions_dict

        return cls.from_dict(merged_data)

    @classmethod
    def from_dict(cls, data: dict) -> 'RapidRotationConfig':
        """
        Load configuration from dictionary

        Args:
            data: Dictionary with config values

        Returns:
            RapidRotationConfig instance

        Example:
            config = RapidRotationConfig.from_dict({
                'min_sl_pct': 2.5,
                'max_positions': 3
            })
        """
        # Handle sessions if present in dict
        if 'sessions' in data and isinstance(data['sessions'], dict):
            sessions_dict = {}
            for session_name, session_data in data['sessions'].items():
                if isinstance(session_data, dict):
                    sessions_dict[session_name] = SessionConfig.from_dict(session_data)
                elif isinstance(session_data, SessionConfig):
                    sessions_dict[session_name] = session_data
            data = {**data, 'sessions': sessions_dict}

        # Filter out keys that don't match dataclass fields
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    def to_dict(self) -> dict:
        """
        Convert to dictionary

        Returns:
            Dict with all config values

        Example:
            config_dict = config.to_dict()
            print(config_dict['min_sl_pct'])
        """
        result = asdict(self)
        # Convert SessionConfig objects to dicts
        if 'sessions' in result:
            result['sessions'] = {
                name: asdict(session) if isinstance(session, SessionConfig) else session
                for name, session in result['sessions'].items()
            }
        return result

    def to_yaml(self, path: str):
        """
        Save configuration to YAML file

        Args:
            path: Path to save YAML file

        Example:
            config.to_yaml('config/trading.yaml')
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        config_dict = self.to_dict()

        # Separate rapid_rotation and legacy for backward compatibility
        rapid_rotation_keys = {
            'atr_sl_multiplier', 'atr_tp_multiplier', 'min_sl_pct', 'max_sl_pct',
            'min_tp_pct', 'max_tp_pct', 'default_sl_pct', 'default_tp_pct',
            'trail_activation_pct', 'trail_lock_pct', 'max_positions', 'max_hold_days',
            'position_size_pct', 'max_position_pct', 'min_score', 'min_atr_pct',
            'regime_filter_enabled', 'regime_sma_period', 'sector_bull_threshold',
            'sector_bear_threshold', 'sector_bull_bonus', 'sector_bear_penalty',
            'sector_sideways_adj',
            # v6.20 Refactor #2: Dynamic sector refresh
            'sector_vix_threshold', 'sector_ttl_volatile_min', 'sector_ttl_normal_min', 'sector_vix_cache_ttl_sec',
            # Alt data
            'alt_data_max_bonus', 'alt_data_max_penalty',
            'daily_loss_limit_pct', 'min_buying_power_pct', 'pdt_account_threshold',
            'pdt_day_trade_limit', 'pdt_reserve', 'pdt_enforce_always', 'max_consecutive_losses',
            'circuit_breaker_pause_hours', 'market_open_hour', 'market_open_minute',
            'market_close_hour', 'market_close_minute', 'pre_close_minute',
            # v6.36: Skip Window
            'skip_window_enabled', 'skip_window_start_hour', 'skip_window_start_minute',
            'skip_window_end_hour', 'skip_window_end_minute',
            'sector_cache_ttl_days', 'price_cache_ttl_seconds',
            # v6.17: Entry Protection fields
            'entry_protection_enabled', 'entry_block_minutes_after_open',
            'entry_allow_discount_exception', 'entry_discount_exception_pct',
            'entry_vwap_max_distance_pct', 'entry_vwap_allow_below',
            'entry_limit_order_only', 'entry_max_chase_pct',
            'entry_limit_timeout_minutes', 'entry_track_rejections',
            # v6.18: Pre-filter Auto-Refresh fields
            'pre_filter_on_demand_enabled', 'pre_filter_on_demand_min_pool',
            'pre_filter_on_demand_zero_signals', 'pre_filter_intraday_enabled',
            'pre_filter_intraday_schedule', 'pre_filter_intraday_minute', 'pre_filter_max_per_day'
        }

        rapid_rotation = {k: v for k, v in config_dict.items() if k in rapid_rotation_keys}
        legacy = {k: v for k, v in config_dict.items() if k not in rapid_rotation_keys and k != 'sessions'}
        sessions = config_dict.get('sessions', {})

        output = {
            'rapid_rotation': rapid_rotation,
            **legacy,
            'sessions': sessions
        }

        with open(path, 'w') as f:
            yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    def validate(self) -> List[str]:
        """
        Validate configuration values (v6.10.1: Enhanced validation)

        Returns:
            List of validation errors (empty if valid)

        Example:
            errors = config.validate()
            if errors:
                print("Invalid config:", errors)
        """
        errors = []

        # =====================================================================
        # STOP LOSS / TAKE PROFIT VALIDATION
        # =====================================================================
        # Range validation
        if self.min_sl_pct <= 0:
            errors.append(f"min_sl_pct must be > 0, got {self.min_sl_pct}")
        elif self.min_sl_pct < 1.0:
            errors.append(f"min_sl_pct too tight (< 1%), got {self.min_sl_pct}% - риск slippage")

        if self.max_sl_pct <= 0:
            errors.append(f"max_sl_pct must be > 0, got {self.max_sl_pct}")
        elif self.max_sl_pct > 10.0:
            errors.append(f"max_sl_pct too wide (> 10%), got {self.max_sl_pct}% - excessive risk")

        if self.min_sl_pct >= self.max_sl_pct:
            errors.append(f"min_sl_pct ({self.min_sl_pct}%) must be < max_sl_pct ({self.max_sl_pct}%)")

        if self.min_tp_pct <= 0:
            errors.append(f"min_tp_pct must be > 0, got {self.min_tp_pct}")

        if self.max_tp_pct <= 0:
            errors.append(f"max_tp_pct must be > 0, got {self.max_tp_pct}")
        elif self.max_tp_pct > 50.0:
            errors.append(f"max_tp_pct too high (> 50%), got {self.max_tp_pct}% - unrealistic target")

        if self.min_tp_pct >= self.max_tp_pct:
            errors.append(f"min_tp_pct ({self.min_tp_pct}%) must be < max_tp_pct ({self.max_tp_pct}%)")

        # Logic validation: TP must be > SL
        if self.min_tp_pct <= self.max_sl_pct:
            errors.append(
                f"min_tp_pct ({self.min_tp_pct}%) must be > max_sl_pct ({self.max_sl_pct}%) "
                f"[Reason: TP target must exceed worst-case SL]"
            )

        # ATR multiplier validation
        if self.atr_sl_multiplier <= 0 or self.atr_sl_multiplier > 5.0:
            errors.append(f"atr_sl_multiplier should be 0-5, got {self.atr_sl_multiplier}")

        if self.atr_tp_multiplier <= 0 or self.atr_tp_multiplier > 10.0:
            errors.append(f"atr_tp_multiplier should be 0-10, got {self.atr_tp_multiplier}")

        if self.atr_tp_multiplier <= self.atr_sl_multiplier:
            errors.append(
                f"atr_tp_multiplier ({self.atr_tp_multiplier}) should be > atr_sl_multiplier ({self.atr_sl_multiplier}) "
                f"[Reason: TP ATR must be wider than SL ATR for positive R:R]"
            )

        # Default fallback values
        if self.default_sl_pct < self.min_sl_pct or self.default_sl_pct > self.max_sl_pct:
            errors.append(
                f"default_sl_pct ({self.default_sl_pct}%) must be within "
                f"[{self.min_sl_pct}%, {self.max_sl_pct}%]"
            )

        if self.default_tp_pct < self.min_tp_pct or self.default_tp_pct > self.max_tp_pct:
            errors.append(
                f"default_tp_pct ({self.default_tp_pct}%) must be within "
                f"[{self.min_tp_pct}%, {self.max_tp_pct}%]"
            )

        # =====================================================================
        # POSITION MANAGEMENT VALIDATION
        # =====================================================================
        if self.max_positions <= 0:
            errors.append(f"max_positions must be > 0, got {self.max_positions}")
        elif self.max_positions > 20:
            errors.append(f"max_positions too high (> 20), got {self.max_positions} - over-diversification")

        if self.max_hold_days <= 0:
            errors.append(f"max_hold_days must be > 0, got {self.max_hold_days}")
        elif self.max_hold_days > 30:
            errors.append(f"max_hold_days too long (> 30), got {self.max_hold_days} - not rapid rotation")

        if self.position_size_pct <= 0:
            errors.append(f"position_size_pct must be > 0, got {self.position_size_pct}")
        elif self.position_size_pct > 100:
            errors.append(f"position_size_pct > 100%, got {self.position_size_pct}% - cannot exceed account")

        if self.max_position_pct <= 0:
            errors.append(f"max_position_pct must be > 0, got {self.max_position_pct}")
        elif self.max_position_pct > 100:
            errors.append(f"max_position_pct > 100%, got {self.max_position_pct}% - cannot exceed account")

        if self.position_size_pct > self.max_position_pct:
            errors.append(
                f"position_size_pct ({self.position_size_pct}%) must be <= "
                f"max_position_pct ({self.max_position_pct}%)"
            )

        # =====================================================================
        # RISK MANAGEMENT VALIDATION
        # =====================================================================
        if self.daily_loss_limit_pct <= 0:
            errors.append(f"daily_loss_limit_pct must be > 0, got {self.daily_loss_limit_pct}")
        elif self.daily_loss_limit_pct > 50:
            errors.append(f"daily_loss_limit_pct too high (> 50%), got {self.daily_loss_limit_pct}% - excessive risk")

        if self.risk_budget_pct <= 0:
            errors.append(f"risk_budget_pct must be > 0, got {self.risk_budget_pct}")
        elif self.risk_budget_pct > 5.0:
            errors.append(f"risk_budget_pct too high (> 5%), got {self.risk_budget_pct}% - excessive per-trade risk")

        # =====================================================================
        # TRAILING STOP VALIDATION
        # =====================================================================
        if self.trail_activation_pct <= 0:
            errors.append(f"trail_activation_pct must be > 0, got {self.trail_activation_pct}")
        # Note: Trailing can activate before TP (it's designed to let winners run beyond TP)
        # So we don't enforce trail_activation_pct >= min_tp_pct

        if self.trail_lock_pct <= 0 or self.trail_lock_pct > 100:
            errors.append(f"trail_lock_pct should be 0-100%, got {self.trail_lock_pct}%")

        # =====================================================================
        # SCORE / VOLATILITY VALIDATION
        # =====================================================================
        if self.min_score < 0 or self.min_score > 100:
            errors.append(f"min_score should be 0-100, got {self.min_score}")

        if self.min_atr_pct <= 0:
            errors.append(f"min_atr_pct must be > 0, got {self.min_atr_pct}")
        elif self.min_atr_pct > 10.0:
            errors.append(f"min_atr_pct too high (> 10%), got {self.min_atr_pct}% - excludes most stocks")

        # =====================================================================
        # PDT VALIDATION
        # =====================================================================
        if self.pdt_day_trade_limit < 0:
            errors.append(f"pdt_day_trade_limit must be >= 0, got {self.pdt_day_trade_limit}")

        if self.pdt_reserve < 0:
            errors.append(f"pdt_reserve must be >= 0, got {self.pdt_reserve}")
        elif self.pdt_reserve > self.pdt_day_trade_limit:
            errors.append(
                f"pdt_reserve ({self.pdt_reserve}) cannot be > pdt_day_trade_limit ({self.pdt_day_trade_limit})"
            )

        if self.pdt_tp_threshold <= 0:
            errors.append(f"pdt_tp_threshold must be > 0, got {self.pdt_tp_threshold}")

        # =====================================================================
        # SESSION VALIDATION
        # =====================================================================
        for session_name, session in self.sessions.items():
            if session.start < 0 or session.start > 1440:
                errors.append(f"Session '{session_name}' start ({session.start}) should be 0-1440 minutes")
            if session.end < 0 or session.end > 1440:
                errors.append(f"Session '{session_name}' end ({session.end}) should be 0-1440 minutes")
            if session.start >= session.end:
                errors.append(
                    f"Session '{session_name}' start ({session.start}) must be < end ({session.end})"
                )
            # v6.11: Allow interval -1 for "once per day" scans (gap scanner)
            if session.interval < -1:
                errors.append(f"Session '{session_name}' interval ({session.interval}) must be >= -1 (-1 = once/day, 0 = monitor, >0 = scan interval)")

        # =====================================================================
        # PRODUCTION GRADE: VIX & SECTOR REFRESH VALIDATION (v6.21)
        # =====================================================================
        if self.sector_vix_threshold < 5 or self.sector_vix_threshold > 50:
            errors.append(
                f"sector_vix_threshold ({self.sector_vix_threshold}) should be 5-50 "
                f"[Reason: VIX < 5 = unrealistic, VIX > 50 = extreme crisis]"
            )

        if self.sector_ttl_volatile_min <= 0 or self.sector_ttl_volatile_min > 60:
            errors.append(
                f"sector_ttl_volatile_min ({self.sector_ttl_volatile_min}) should be 1-60 minutes "
                f"[Reason: < 1 = too frequent API calls, > 60 = stale data]"
            )

        if self.sector_ttl_normal_min <= 0 or self.sector_ttl_normal_min > 60:
            errors.append(
                f"sector_ttl_normal_min ({self.sector_ttl_normal_min}) should be 1-60 minutes "
                f"[Reason: < 1 = too frequent API calls, > 60 = stale data]"
            )

        if self.sector_vix_cache_ttl_sec < 10 or self.sector_vix_cache_ttl_sec > 300:
            errors.append(
                f"sector_vix_cache_ttl_sec ({self.sector_vix_cache_ttl_sec}) should be 10-300 seconds "
                f"[Reason: < 10s = excessive API calls, > 300s (5 min) = stale VIX]"
            )

        if self.sector_ttl_volatile_min > self.sector_ttl_normal_min:
            errors.append(
                f"sector_ttl_volatile_min ({self.sector_ttl_volatile_min}) should be <= "
                f"sector_ttl_normal_min ({self.sector_ttl_normal_min}) "
                f"[Reason: Volatile markets need FASTER refresh, not slower]"
            )

        # =====================================================================
        # PRODUCTION GRADE: ENTRY PROTECTION VALIDATION (v6.21)
        # =====================================================================
        if self.entry_vwap_max_distance_pct <= 0 or self.entry_vwap_max_distance_pct > 10:
            errors.append(
                f"entry_vwap_max_distance_pct ({self.entry_vwap_max_distance_pct}%) should be 0.1-10% "
                f"[Reason: < 0.1% = too strict, > 10% = defeats purpose]"
            )

        if self.entry_max_chase_pct < 0 or self.entry_max_chase_pct > 2:
            errors.append(
                f"entry_max_chase_pct ({self.entry_max_chase_pct}%) should be 0-2% "
                f"[Reason: < 0% = invalid, > 2% = excessive slippage]"
            )

        if self.entry_limit_timeout_minutes <= 0 or self.entry_limit_timeout_minutes > 30:
            errors.append(
                f"entry_limit_timeout_minutes ({self.entry_limit_timeout_minutes}) should be 1-30 minutes "
                f"[Reason: < 1 = too tight, > 30 = signal may be stale]"
            )

        return errors

    def __post_init__(self):
        """Initialize defaults and validate config after initialization"""
        # Set default for pre_filter_intraday_schedule if None
        if self.pre_filter_intraday_schedule is None:
            object.__setattr__(self, 'pre_filter_intraday_schedule', [10, 13, 15])

        # Validate
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid configuration: {'; '.join(errors)}")


# =========================================================================
# DEFAULT INSTANCE (for backward compatibility)
# =========================================================================
DEFAULT_CONFIG = RapidRotationConfig()


def load_config(path: Optional[str] = None) -> RapidRotationConfig:
    """
    Load configuration with fallback to defaults

    Args:
        path: Optional path to YAML config file

    Returns:
        RapidRotationConfig instance

    Example:
        # Load from file (with fallback to defaults)
        config = load_config('config/trading.yaml')

        # Use defaults
        config = load_config()
    """
    if path and os.path.exists(path):
        try:
            return RapidRotationConfig.from_yaml(path)
        except Exception as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration")

    return RapidRotationConfig()
