"""
SQLAlchemy ORM models — matches existing SQLite schema exactly.

All models use __tablename__ to map to existing tables.
Column types match the actual DB columns (TEXT for dates in SQLite).
"""

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
)

from database.orm.base import Base


# ==========================================================================
# Core Trading
# ==========================================================================


class ActivePosition(Base):
    __tablename__ = "active_positions"

    symbol = Column(Text, primary_key=True)
    entry_date = Column(Text, nullable=False)
    entry_price = Column(Float, nullable=False)
    qty = Column(Integer, nullable=False)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    peak_price = Column(Float)
    trough_price = Column(Float)
    trailing_stop = Column(Integer, default=0)
    day_held = Column(Integer, default=0)
    sl_pct = Column(Float)
    tp_pct = Column(Float)
    entry_atr_pct = Column(Float)
    sl_order_id = Column(Text)
    tp_order_id = Column(Text)
    entry_order_id = Column(Text)
    sector = Column(Text)
    source = Column(Text)
    signal_score = Column(Integer)
    mode = Column(Text)
    regime = Column(Text)
    entry_rsi = Column(Float)
    momentum_5d = Column(Float)
    updated_at = Column(Text)

    def __repr__(self):
        return f"<ActivePosition {self.symbol} qty={self.qty} entry={self.entry_price}>"


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Text, primary_key=True)
    timestamp = Column(Text)
    date = Column(Text)
    action = Column(Text)
    symbol = Column(Text)
    qty = Column(Integer)
    price = Column(Float)
    reason = Column(Text)
    entry_price = Column(Float)
    pnl_usd = Column(Float)
    pnl_pct = Column(Float)
    hold_duration = Column(Text)
    pdt_used = Column(Integer)
    pdt_remaining = Column(Integer)
    day_held = Column(Integer)
    mode = Column(Text)
    regime = Column(Text)
    spy_price = Column(Float)
    signal_score = Column(Float)
    gap_pct = Column(Float)
    atr_pct = Column(Float)
    from_queue = Column(Integer)
    version = Column(Text)
    source = Column(Text)
    full_data = Column(Text)
    volume_ratio = Column(Float)
    composite_score = Column(Float)
    mfe_pct = Column(Float)
    mae_pct = Column(Float)
    hold_minutes = Column(Integer)
    exit_vs_vwap_pct = Column(Float)
    pct_from_mfe_to_close = Column(Float)
    next_day_open_pct = Column(Float)
    signal_source = Column(Text)
    entry_rsi = Column(Float)
    entry_vix = Column(Float)
    new_score = Column(Float)
    momentum_20d = Column(Float)
    distance_from_high = Column(Float)
    sector = Column(Text)
    mfe_timestamp = Column(Text)
    sl_multiplier = Column(Float)
    sl_method = Column(Text)
    trail_activation_pct = Column(Float)
    trail_lock_pct = Column(Float)
    tp_pct = Column(Float)
    fill_time_sec = Column(Float)
    slippage_pct = Column(Float)
    bounce_pct_from_lod = Column(Float)

    def __repr__(self):
        return f"<Trade {self.id} {self.action} {self.symbol} pnl={self.pnl_usd}>"


class TradeEvent(Base):
    __tablename__ = "trade_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    price = Column(Float)
    qty = Column(Integer)
    pnl_pct = Column(Float, default=0)
    pnl_usd = Column(Float, default=0)
    strategy = Column(Text, default="")
    reason = Column(Text, default="")
    created_at = Column(Text, nullable=False)
    notified = Column(Integer, default=0)

    def __repr__(self):
        return f"<TradeEvent {self.event_type} {self.symbol} @ {self.created_at}>"


class PDTEntry(Base):
    __tablename__ = "pdt_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text)
    entry_date = Column(Text)
    exit_date = Column(Text)
    same_day_exit = Column(Integer)

    def __repr__(self):
        return f"<PDTEntry {self.symbol} {self.entry_date}>"


# ==========================================================================
# Stock Data
# ==========================================================================


class StockOHLC(Base):
    __tablename__ = "stock_daily_ohlc"

    # No single PK in original schema — use composite + rowid.
    symbol = Column(Text, primary_key=True)
    date = Column(Text, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Integer)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_stock_daily_ohlc"),
    )

    def __repr__(self):
        return f"<StockOHLC {self.symbol} {self.date} c={self.close}>"


class StockFundamentals(Base):
    __tablename__ = "stock_fundamentals"

    symbol = Column(Text, primary_key=True)
    pe_trailing = Column(Float)
    pe_forward = Column(Float)
    beta = Column(Float)
    float_shares = Column(Integer)
    shares_out = Column(Integer)
    market_cap = Column(Integer)
    avg_volume = Column(Integer)
    sector = Column(Text)
    industry = Column(Text)
    updated_at = Column(Text)

    def __repr__(self):
        return f"<StockFundamentals {self.symbol} sector={self.sector} mcap={self.market_cap}>"


class IntradayBar5m(Base):
    __tablename__ = "intraday_bars_5m"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    timestamp = Column(Text, nullable=False)
    date = Column(Text, nullable=False)
    time_et = Column(Text, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Integer)
    vwap = Column(Float)
    n_trades = Column(Integer)
    created_at = Column(Text)

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uq_intraday_bars_5m"),
    )

    def __repr__(self):
        return f"<IntradayBar5m {self.symbol} {self.timestamp}>"


class IntradaySnapshot(Base):
    __tablename__ = "intraday_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False)
    time_et = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    price = Column(Float)
    volume = Column(Integer)
    vwap = Column(Float)
    open_price = Column(Float)
    high = Column(Float)
    low = Column(Float)
    signal_source = Column(Text)
    action_taken = Column(Text)
    scan_price = Column(Float)
    pct_from_scan = Column(Float)
    created_at = Column(Text)
    spy_price = Column(Float)
    vix_at_time = Column(Float)
    unrealized_pnl_pct = Column(Float)
    pct_to_sl = Column(Float)
    vs_spy_rs = Column(Float)
    sector_etf_pct = Column(Float)

    def __repr__(self):
        return f"<IntradaySnapshot {self.symbol} {self.date} {self.time_et}>"


# ==========================================================================
# Market Data
# ==========================================================================


class MacroSnapshot(Base):
    __tablename__ = "macro_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False, unique=True)
    yield_10y = Column(Float)
    yield_3m = Column(Float)
    yield_spread = Column(Float)
    vix_close = Column(Float)
    spy_close = Column(Float)
    dxy_close = Column(Float)
    collected_at = Column(Text)
    vix3m_close = Column(Float)
    dxy_change_pct = Column(Float)
    regime_label = Column(Text)
    spy_regime = Column(Text)
    gold_close = Column(Float)
    crude_close = Column(Float)
    hyg_close = Column(Float)
    btc_close = Column(Float)
    usdjpy_close = Column(Float)
    skew_close = Column(Float)
    vvix_close = Column(Float)
    copper_close = Column(Float)
    tlt_close = Column(Float)
    lqd_close = Column(Float)
    eem_close = Column(Float)
    ief_close = Column(Float)

    def __repr__(self):
        return f"<MacroSnapshot {self.date} vix={self.vix_close} spy={self.spy_close}>"


class MarketBreadth(Base):
    __tablename__ = "market_breadth"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False, unique=True)
    pct_above_20d_ma = Column(Float)
    pct_above_50d_ma = Column(Float)
    advance_count = Column(Integer)
    decline_count = Column(Integer)
    unchanged_count = Column(Integer)
    ad_ratio = Column(Float)
    new_52w_highs = Column(Integer)
    new_52w_lows = Column(Integer)
    total_symbols = Column(Integer)
    updated_at = Column(Text)

    def __repr__(self):
        return f"<MarketBreadth {self.date} adv={self.advance_count} dec={self.decline_count}>"


class SectorETFReturn(Base):
    __tablename__ = "sector_etf_daily_returns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False)
    etf = Column(Text, nullable=False)
    sector = Column(Text)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Integer)
    pct_change = Column(Float)
    vs_spy = Column(Float)
    created_at = Column(Text)

    __table_args__ = (
        UniqueConstraint("date", "etf", name="uq_sector_etf_daily_returns"),
    )

    def __repr__(self):
        return f"<SectorETFReturn {self.date} {self.etf} pct={self.pct_change}>"


# ==========================================================================
# News & Signals
# ==========================================================================


class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    published_at = Column(Text, nullable=False)
    collected_at = Column(Text, nullable=False)
    market_session = Column(Text)
    scan_date_et = Column(Text)
    source = Column(Text, nullable=False)
    source_id = Column(Text)
    url = Column(Text)
    symbol = Column(Text)
    symbols_mentioned = Column(Text)
    headline = Column(Text, nullable=False)
    summary = Column(Text)
    category = Column(Text)
    event_type = Column(Text)
    sectors_affected = Column(Text)
    sentiment_score = Column(Float)
    sentiment_label = Column(Text)
    impact_score = Column(Float)
    vix_at_time = Column(Float)
    spy_price_at_time = Column(Float)
    raw_json = Column(Text)
    content_hash = Column(Text, unique=True)

    def __repr__(self):
        return f"<NewsEvent {self.id} {self.symbol} {self.headline[:40] if self.headline else ''}>"


class EarningsHistory(Base):
    __tablename__ = "earnings_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    report_date = Column(Text, nullable=False)
    timing = Column(Text)  # AMC / BMO / None
    eps_estimate = Column(Float)
    eps_actual = Column(Float)
    surprise_pct = Column(Float)
    updated_date = Column(Text, nullable=False)
    created_at = Column(Text)

    __table_args__ = (
        UniqueConstraint("symbol", "report_date", name="uq_earnings_history"),
    )

    def __repr__(self):
        return f"<EarningsHistory {self.symbol} {self.report_date} {self.timing}>"


class AnalystRating(Base):
    __tablename__ = "analyst_ratings_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    date = Column(Text, nullable=False)
    firm = Column(Text)
    to_grade = Column(Text)
    from_grade = Column(Text)
    action = Column(Text)
    price_target = Column(Float)
    prior_price_target = Column(Float)

    __table_args__ = (
        UniqueConstraint("symbol", "date", "firm", name="uq_analyst_ratings_history"),
    )

    def __repr__(self):
        return f"<AnalystRating {self.symbol} {self.date} {self.firm} -> {self.to_grade}>"


class AnalystConsensus(Base):
    __tablename__ = "analyst_consensus"

    symbol = Column(Text, primary_key=True)
    updated_at = Column(Text, nullable=False)
    strong_buy = Column(Integer)
    buy = Column(Integer)
    hold = Column(Integer)
    sell = Column(Integer)
    strong_sell = Column(Integer)
    total_analysts = Column(Integer)
    bull_score = Column(Float)
    target_mean = Column(Float)
    target_high = Column(Float)
    target_low = Column(Float)
    target_median = Column(Float)
    upside_pct = Column(Float)

    def __repr__(self):
        return f"<AnalystConsensus {self.symbol} bull={self.bull_score} upside={self.upside_pct}%>"


class InsiderTransaction(Base):
    __tablename__ = "insider_transactions_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    filing_date = Column(Text)
    trade_date = Column(Text, nullable=False)
    insider_name = Column(Text)
    insider_title = Column(Text)
    transaction_type = Column(Text)
    shares = Column(Integer)
    price = Column(Float)
    value = Column(Float)
    source = Column(Text, default="yfinance")

    __table_args__ = (
        UniqueConstraint(
            "symbol", "trade_date", "insider_name", "transaction_type", "shares",
            name="uq_insider_transactions_history",
        ),
    )

    def __repr__(self):
        return f"<InsiderTransaction {self.symbol} {self.trade_date} {self.transaction_type}>"


class OptionsDailySummary(Base):
    __tablename__ = "options_daily_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    collected_date = Column(Text, nullable=False)
    total_call_volume = Column(Integer)
    total_put_volume = Column(Integer)
    pc_volume_ratio = Column(Float)
    total_call_oi = Column(Integer)
    total_put_oi = Column(Integer)
    pc_oi_ratio = Column(Float)
    avg_call_iv = Column(Float)
    avg_put_iv = Column(Float)
    iv_skew = Column(Float)
    unusual_call_count = Column(Integer)
    unusual_put_count = Column(Integer)
    max_call_volume = Column(Integer)
    max_put_volume = Column(Integer)
    n_contracts = Column(Integer)

    __table_args__ = (
        UniqueConstraint("symbol", "collected_date", name="uq_options_daily_summary"),
    )

    def __repr__(self):
        return f"<OptionsDailySummary {self.symbol} {self.collected_date} pc={self.pc_volume_ratio}>"


class ShortInterest(Base):
    __tablename__ = "short_interest"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    date = Column(Text, nullable=False)
    short_pct_float = Column(Float)
    short_ratio = Column(Float)
    shares_short = Column(Integer)
    shares_short_prior = Column(Integer)
    short_change_pct = Column(Float)
    updated_at = Column(Text)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_short_interest"),
    )

    def __repr__(self):
        return f"<ShortInterest {self.symbol} {self.date} pct={self.short_pct_float}>"


# ==========================================================================
# Discovery
# ==========================================================================


class DiscoveryPick(Base):
    __tablename__ = "discovery_picks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_date = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    scan_price = Column(Float, nullable=False)
    current_price = Column(Float)
    layer2_score = Column(Float)
    beta = Column(Float)
    atr_pct = Column(Float)
    distance_from_high = Column(Float)
    rsi = Column(Float)
    momentum_5d = Column(Float)
    momentum_20d = Column(Float)
    volume_ratio = Column(Float)
    sl_price = Column(Float)
    sl_pct = Column(Float)
    tp1_price = Column(Float)
    tp1_pct = Column(Float)
    tp2_price = Column(Float)
    tp2_pct = Column(Float)
    sector = Column(Text)
    market_cap = Column(Float)
    vix_close = Column(Float)
    pct_above_20d_ma = Column(Float)
    status = Column(Text, default="active")
    created_at = Column(Text)
    updated_at = Column(Text)
    vix_term_structure = Column(Float)
    new_52w_highs = Column(Float)
    bull_score = Column(Float)
    news_count = Column(Float)
    news_pos_ratio = Column(Float)
    highs_lows_ratio = Column(Float)
    ad_ratio = Column(Float)
    mcap_log = Column(Float)
    sector_1d_change = Column(Float)
    vix3m_close = Column(Float)
    upside_pct = Column(Float)
    outcome_1d = Column(Float)
    outcome_2d = Column(Float)
    outcome_3d = Column(Float)
    outcome_5d = Column(Float)
    outcome_max_gain_5d = Column(Float)
    outcome_max_dd_5d = Column(Float)
    days_to_earnings = Column(Integer)
    put_call_ratio = Column(Float)
    short_pct_float = Column(Float)
    benchmark_xlu_5d = Column(Float)
    benchmark_xle_5d = Column(Float)
    benchmark_spy_5d = Column(Float)
    breadth_delta_5d = Column(Float)
    vix_delta_5d = Column(Float)
    crude_close = Column(Float)
    gold_close = Column(Float)
    dxy_delta_5d = Column(Float)
    stress_score = Column(Float)
    hyg_close = Column(Float)
    expected_gain = Column(Float, default=0.0)
    rr_ratio = Column(Float, default=0.0)
    distance_from_20d_high = Column(Float)
    premarket_price = Column(Float)
    gap_pct = Column(Float)
    scan_type = Column(Text, default="evening")
    limit_entry_price = Column(Float)
    limit_pct = Column(Float)
    entry_price = Column(Float)
    entry_status = Column(Text, default="pending")
    entry_filled_at = Column(Text)
    tp_timeline_json = Column(Text)
    weekend_play_json = Column(Text)
    ensemble_json = Column(Text)
    council_json = Column(Text)
    ubrain_prob = Column(Float)

    __table_args__ = (
        UniqueConstraint("scan_date", "symbol", name="uq_discovery_picks"),
    )

    def __repr__(self):
        return f"<DiscoveryPick {self.scan_date} {self.symbol} score={self.layer2_score}>"


class DiscoveryOutcome(Base):
    __tablename__ = "discovery_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_date = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    predicted_er = Column(Float)
    predicted_wr = Column(Float)
    actual_return_d3 = Column(Float)
    actual_return_d5 = Column(Float)
    max_gain = Column(Float)
    max_dd = Column(Float)
    tp_hit = Column(Integer)
    sl_hit = Column(Integer)
    regime = Column(Text)
    atr_pct = Column(Float)
    sector = Column(Text)
    vix_close = Column(Float)
    scan_price = Column(Float)
    exit_price = Column(Float)
    created_at = Column(Text)

    __table_args__ = (
        UniqueConstraint("scan_date", "symbol", name="uq_discovery_outcomes"),
    )

    def __repr__(self):
        return f"<DiscoveryOutcome {self.scan_date} {self.symbol} d5={self.actual_return_d5}>"


class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Text, nullable=False)
    scan_date = Column(Text, nullable=False)
    scan_type = Column(Text)
    symbol = Column(Text, nullable=False)
    signal_rank = Column(Integer)
    action_taken = Column(Text)
    score = Column(Integer)
    signal_source = Column(Text)
    scan_price = Column(Float)
    outcome_1d = Column(Float)
    outcome_2d = Column(Float)
    outcome_3d = Column(Float)
    outcome_4d = Column(Float)
    outcome_5d = Column(Float)
    outcome_max_gain_5d = Column(Float)
    outcome_max_dd_5d = Column(Float)
    tracked_at = Column(Text, nullable=False)
    updated_at = Column(Text)
    skip_reason = Column(Text)
    days_until_earnings = Column(Integer)
    earnings_gap_pct = Column(Float)
    volume_ratio = Column(Float)
    atr_pct = Column(Float)
    entry_rsi = Column(Float)
    momentum_5d = Column(Float)
    gap_pct = Column(Float)
    gap_confidence = Column(Integer)
    momentum_20d = Column(Float)
    distance_from_high = Column(Float)
    vix_at_signal = Column(Float)
    spy_pct_above_sma = Column(Float)
    sector_1d_change = Column(Float)
    distance_from_20d_high = Column(Float)
    new_score = Column(Float)
    timing = Column(Text)
    eps_surprise_pct = Column(Float)
    close_to_high_pct = Column(Float)
    spy_intraday_pct = Column(Float)
    sector_5d_return = Column(Float)
    vix_1w_change = Column(Float)
    entry_vs_open_pct = Column(Float)
    entry_vs_vwap_pct = Column(Float)
    bounce_pct_from_lod = Column(Float)
    num_positions_open = Column(Integer)
    first_5min_return = Column(Float)
    intraday_spy_trend = Column(Float)
    spy_rsi_at_scan = Column(Float)
    pm_range_pct = Column(Float)
    sector = Column(Text)
    trade_id = Column(Text)
    margin_to_rsi = Column(Float)
    margin_to_atr = Column(Float)
    margin_to_score = Column(Float)
    margin_to_vix_skip = Column(Float)
    short_percent_of_float = Column(Float)
    catalyst_type = Column(Text)
    news_sentiment = Column(Text)
    news_impact_score = Column(Float)
    first_30min_return = Column(Float)
    insider_buy_30d_value = Column(Float)
    insider_buy_days_ago = Column(Integer)
    entry_time_et = Column(Text)
    consecutive_down_days = Column(Integer)
    sector_etf_1d_pct = Column(Float)
    distance_from_200d_ma = Column(Float)
    earnings_beat_streak = Column(Integer)
    analyst_action_7d = Column(Text)
    analyst_target_upside = Column(Float)
    analyst_rating_count_30d = Column(Integer)
    analyst_bull_score = Column(Float)
    ubrain_prob = Column(Float)

    __table_args__ = (
        UniqueConstraint("scan_id", "symbol", name="uq_signal_outcomes_scan"),
    )

    def __repr__(self):
        return f"<SignalOutcome {self.scan_date} {self.symbol} {self.action_taken}>"


class BackfillSignalOutcome(Base):
    __tablename__ = "backfill_signal_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_date = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    sector = Column(Text)
    scan_price = Column(Float)
    atr_pct = Column(Float)
    entry_rsi = Column(Float)
    distance_from_20d_high = Column(Float)
    momentum_5d = Column(Float)
    momentum_20d = Column(Float)
    volume_ratio = Column(Float)
    vix_at_signal = Column(Float)
    outcome_1d = Column(Float)
    outcome_2d = Column(Float)
    outcome_3d = Column(Float)
    outcome_4d = Column(Float)
    outcome_5d = Column(Float)
    outcome_max_gain_5d = Column(Float)
    outcome_max_dd_5d = Column(Float)

    __table_args__ = (
        UniqueConstraint("scan_date", "symbol", name="uq_backfill_signal_outcomes"),
    )

    def __repr__(self):
        return f"<BackfillSignalOutcome {self.scan_date} {self.symbol}>"


class AdaptiveParameter(Base):
    __tablename__ = "adaptive_parameters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sector = Column(Text, nullable=False)
    regime = Column(Text, nullable=False)
    param_name = Column(Text, nullable=False)
    param_value = Column(Float, nullable=False)
    n_signals = Column(Integer)
    metric_value = Column(Float)
    fit_date = Column(Text)
    created_at = Column(Text)

    __table_args__ = (
        UniqueConstraint("sector", "regime", "param_name", name="uq_adaptive_parameters"),
    )

    def __repr__(self):
        return f"<AdaptiveParameter {self.sector}/{self.regime} {self.param_name}={self.param_value}>"


class StrategyFitStat(Base):
    __tablename__ = "strategy_fit_stats"

    condition = Column(Text, nullable=False, primary_key=True)
    strategy_name = Column(Text, nullable=False, primary_key=True)
    sharpe = Column(Float)
    avg_return = Column(Float)
    win_rate = Column(Float)
    n = Column(Integer)
    fit_date = Column(Text)

    __table_args__ = (
        UniqueConstraint("condition", "strategy_name", name="uq_strategy_fit_stats"),
    )

    def __repr__(self):
        return f"<StrategyFitStat {self.condition} {self.strategy_name} wr={self.win_rate}>"


class StrategyLearnedParam(Base):
    __tablename__ = "strategy_learned_params"

    strategy_name = Column(Text, primary_key=True)
    params_json = Column(Text, nullable=False)
    fit_date = Column(Text)

    def __repr__(self):
        return f"<StrategyLearnedParam {self.strategy_name}>"


class GapScannerModel(Base):
    __tablename__ = "gap_scanner_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fit_date = Column(Text)
    data_json = Column(Text)
    created_at = Column(Text)
    model_pickle = Column(LargeBinary)

    def __repr__(self):
        return f"<GapScannerModel {self.id} {self.fit_date}>"


class GapPMCache(Base):
    __tablename__ = "gap_pm_cache"

    date = Column(Text, primary_key=True)
    data_json = Column(Text)

    def __repr__(self):
        return f"<GapPMCache {self.date}>"


# ==========================================================================
# Pre-market & Daytrade
# ==========================================================================


class PremarketAnalysis(Base):
    __tablename__ = "premarket_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    date = Column(Text, nullable=False)
    prev_close = Column(Float)
    premarket_gap_pct = Column(Float)
    premarket_high_pct = Column(Float)
    premarket_low_pct = Column(Float)
    premarket_vol = Column(Integer)
    premarket_vol_ratio = Column(Float)
    first_5min_open = Column(Float)
    first_5min_close = Column(Float)
    first_5min_return = Column(Float)
    first_5min_vol = Column(Integer)
    first_30min_return = Column(Float)
    open_vs_pm_high_pct = Column(Float)
    updated_at = Column(Text)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_premarket_analysis"),
    )

    def __repr__(self):
        return f"<PremarketAnalysis {self.symbol} {self.date} gap={self.premarket_gap_pct}>"


class DaytradeOutcome(Base):
    __tablename__ = "daytrade_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    date = Column(Text, nullable=False)
    orb_open = Column(Float)
    orb_high = Column(Float)
    orb_low = Column(Float)
    orb_close = Column(Float)
    orb_range_pct = Column(Float)
    orb_direction = Column(Text)
    orb_vol = Column(Integer)
    entry_price = Column(Float)
    entry_vs_orb = Column(Text)
    entry_vs_vwap = Column(Text)
    vwap_at_entry = Column(Float)
    exit_a = Column(Text)
    pnl_a = Column(Float)
    min_a = Column(Integer)
    exit_b = Column(Text)
    pnl_b = Column(Float)
    min_b = Column(Integer)
    exit_c = Column(Text)
    pnl_c = Column(Float)
    min_c = Column(Integer)
    exit_d = Column(Text)
    pnl_d = Column(Float)
    min_d = Column(Integer)
    eod_price = Column(Float)
    eod_pnl_pct = Column(Float)
    mfe_pct = Column(Float)
    mae_pct = Column(Float)
    mfe_time = Column(Text)
    mae_time = Column(Text)
    premarket_gap_pct = Column(Float)
    first_5min_return = Column(Float)
    first_30min_return = Column(Float)
    premarket_vol_ratio = Column(Float)
    updated_at = Column(Text)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_daytrade_outcomes"),
    )

    def __repr__(self):
        return f"<DaytradeOutcome {self.symbol} {self.date} eod={self.eod_pnl_pct}>"


# ==========================================================================
# Rejections (Counterfactual Analysis)
# ==========================================================================


class ScreenerRejection(Base):
    __tablename__ = "screener_rejections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_date = Column(Text, nullable=False)
    scan_time = Column(Text)
    screener = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    reject_reason = Column(Text, nullable=False)
    scan_price = Column(Float)
    gap_pct = Column(Float)
    volume_ratio = Column(Float)
    rsi = Column(Float)
    momentum_5d = Column(Float)
    atr_pct = Column(Float)
    distance_from_high = Column(Float)
    score = Column(Integer)
    outcome_1d = Column(Float)
    outcome_2d = Column(Float)
    outcome_3d = Column(Float)
    outcome_4d = Column(Float)
    outcome_5d = Column(Float)
    outcome_max_gain_5d = Column(Float)
    outcome_max_dd_5d = Column(Float)
    created_at = Column(Text)
    sector = Column(Text)
    momentum_20d = Column(Float)
    distance_from_20d_high = Column(Float)
    new_score = Column(Float)
    catalyst_type = Column(Text)
    first_30min_return = Column(Float)
    insider_buy_30d_value = Column(Float)
    insider_buy_days_ago = Column(Integer)
    distance_from_20d_ma = Column(Float)
    first_15min_volume_ratio = Column(Float)
    consecutive_down_days = Column(Integer)
    sector_etf_1d_pct = Column(Float)
    distance_from_200d_ma = Column(Float)
    news_sentiment = Column(Text)
    news_impact_score = Column(Float)

    def __repr__(self):
        return f"<ScreenerRejection {self.scan_date} {self.symbol} {self.reject_reason}>"


class PreFilterRejection(Base):
    __tablename__ = "pre_filter_rejections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_date = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    sector = Column(Text)
    reject_reason = Column(Text, nullable=False)
    close_price = Column(Float)
    atr_pct = Column(Float)
    rsi = Column(Float)
    return_5d = Column(Float)
    dollar_volume = Column(Float)
    outcome_1d = Column(Float)
    outcome_2d = Column(Float)
    outcome_3d = Column(Float)
    outcome_4d = Column(Float)
    outcome_5d = Column(Float)
    outcome_max_gain_5d = Column(Float)
    outcome_max_dd_5d = Column(Float)
    created_at = Column(Text)

    def __repr__(self):
        return f"<PreFilterRejection {self.scan_date} {self.symbol} {self.reject_reason}>"


# ==========================================================================
# System / Infrastructure
# ==========================================================================


class EngineHeartbeat(Base):
    __tablename__ = "engine_heartbeat"

    id = Column(Integer, primary_key=True, default=1)
    timestamp = Column(Text, nullable=False)
    alive = Column(Integer, nullable=False, default=1)
    state = Column(Text)
    positions = Column(Integer, default=0)
    running = Column(Integer, default=1)
    updated_at = Column(Text, nullable=False)

    def __repr__(self):
        return f"<EngineHeartbeat alive={self.alive} state={self.state}>"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(Text, nullable=False)
    active = Column(Integer, default=1)
    resolved_at = Column(Text)
    alert_metadata = Column("metadata", Text)
    created_at = Column(Text)

    def __repr__(self):
        return f"<Alert {self.level} {self.message[:40]}>"


class SectorCache(Base):
    __tablename__ = "sector_cache"

    symbol = Column(Text, primary_key=True)
    sector = Column(Text, nullable=False)
    ts = Column(Float, nullable=False)
    status = Column(Text, default="active")
    updated_at = Column(Text, nullable=False)

    def __repr__(self):
        return f"<SectorCache {self.symbol} -> {self.sector}>"


class UniverseStock(Base):
    __tablename__ = "universe_stocks"

    symbol = Column(Text, primary_key=True)
    sector = Column(Text)
    status = Column(Text, default="active")
    ts = Column(Float)
    dollar_vol = Column(Float)
    updated_at = Column(Text, nullable=False)

    def __repr__(self):
        return f"<UniverseStock {self.symbol} sector={self.sector}>"


class PreFilterSession(Base):
    __tablename__ = "pre_filter_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_type = Column(Text, nullable=False)
    scan_time = Column(Text, nullable=False)
    pool_size = Column(Integer, nullable=False, default=0)
    total_scanned = Column(Integer, nullable=False, default=0)
    status = Column(Text, nullable=False, default="running")
    is_ready = Column(Boolean, nullable=False, default=False)
    duration_seconds = Column(Float)
    error_message = Column(Text)
    created_at = Column(Text, nullable=False)

    def __repr__(self):
        return f"<PreFilterSession {self.scan_type} {self.status} pool={self.pool_size}>"


class DeadLetterQueue(Base):
    __tablename__ = "dead_letter_queue"

    id = Column(Text, primary_key=True)
    operation_type = Column(Text, nullable=False)
    operation_data = Column(Text, nullable=False)
    error = Column(Text, nullable=False)
    context = Column(Text)
    status = Column(Text, nullable=False, default="pending")
    created_at = Column(Text, nullable=False)
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(Text)
    resolved_at = Column(Text)
    resolution_note = Column(Text)
    next_retry_at = Column(Text)

    def __repr__(self):
        return f"<DeadLetterQueue {self.id} {self.operation_type} {self.status}>"


# ==========================================================================
# Loss & Risk Tracking
# ==========================================================================


class LossTracking(Base):
    __tablename__ = "loss_tracking"

    id = Column(Integer, primary_key=True, default=1)
    consecutive_losses = Column(Integer, nullable=False, default=0)
    weekly_realized_pnl = Column(Float, nullable=False, default=0.0)
    weekly_reset_date = Column(Text)
    cooldown_until = Column(Text)
    updated_at = Column(Text, nullable=False)
    saved_at = Column(Text)

    def __repr__(self):
        return f"<LossTracking losses={self.consecutive_losses} pnl={self.weekly_realized_pnl}>"


class SectorLossTracking(Base):
    __tablename__ = "sector_loss_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy = Column(Text, nullable=False, default="dip_bounce")
    sector = Column(Text, nullable=False)
    losses = Column(Integer, nullable=False, default=0)
    cooldown_until = Column(Text)
    updated_at = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("strategy", "sector", name="uq_sector_loss_tracking"),
    )

    def __repr__(self):
        return f"<SectorLossTracking {self.strategy}:{self.sector} losses={self.losses}>"


# ==========================================================================
# PDT Tracking
# ==========================================================================


class PDTTracking(Base):
    __tablename__ = "pdt_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False, unique=True)
    entry_date = Column(Text, nullable=False)
    entry_time = Column(Text)
    exit_date = Column(Text)
    exit_time = Column(Text)
    same_day_exit = Column(Integer, default=0)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text)

    def __repr__(self):
        return f"<PDTTracking {self.symbol} entry={self.entry_date}>"


# ==========================================================================
# Outcome Tracking
# ==========================================================================


class SellOutcome(Base):
    __tablename__ = "sell_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Text, nullable=False, unique=True)
    symbol = Column(Text, nullable=False)
    sell_date = Column(Text, nullable=False)
    sell_price = Column(Float, nullable=False)
    sell_reason = Column(Text)
    sell_pnl_pct = Column(Float)
    post_sell_close_1d = Column(Float)
    post_sell_close_3d = Column(Float)
    post_sell_close_5d = Column(Float)
    post_sell_max_5d = Column(Float)
    post_sell_min_5d = Column(Float)
    post_sell_pnl_pct_1d = Column(Float)
    post_sell_pnl_pct_5d = Column(Float)
    tracked_at = Column(Text, nullable=False)
    updated_at = Column(Text)
    buy_trade_id = Column(Text)

    def __repr__(self):
        return f"<SellOutcome {self.trade_id} {self.symbol} pnl={self.sell_pnl_pct}>"


class RejectedOutcome(Base):
    __tablename__ = "rejected_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Text, nullable=False)
    scan_date = Column(Text, nullable=False)
    scan_type = Column(Text)
    symbol = Column(Text, nullable=False)
    signal_rank = Column(Integer)
    rejection_reason = Column(Text)
    score = Column(Integer)
    signal_source = Column(Text)
    scan_price = Column(Float)
    outcome_1d = Column(Float)
    outcome_2d = Column(Float)
    outcome_3d = Column(Float)
    outcome_4d = Column(Float)
    outcome_5d = Column(Float)
    outcome_max_gain_5d = Column(Float)
    outcome_max_dd_5d = Column(Float)
    tracked_at = Column(Text, nullable=False)
    updated_at = Column(Text)
    volume_ratio = Column(Float)
    atr_pct = Column(Float)
    entry_rsi = Column(Float)
    momentum_5d = Column(Float)
    gap_pct = Column(Float)
    gap_confidence = Column(Integer)

    __table_args__ = (
        UniqueConstraint("scan_id", "symbol", name="uq_rejected_outcomes"),
    )

    def __repr__(self):
        return f"<RejectedOutcome {self.scan_date} {self.symbol} {self.rejection_reason}>"


# ==========================================================================
# Earnings Calendar
# ==========================================================================


class EarningsCalendar(Base):
    __tablename__ = "earnings_calendar"

    symbol = Column(Text, primary_key=True)
    next_earnings_date = Column(Text)
    fetched_at = Column(Text, nullable=False)

    def __repr__(self):
        return f"<EarningsCalendar {self.symbol} next={self.next_earnings_date}>"



class SignalQueue(Base):
    __tablename__ = "signal_queue"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(Text)
    scan_date = Column(Text)
    signal_type = Column(Text)
    score = Column(Float)
    data_json = Column(Text)
    status = Column(Text, default='pending')
    queued_at = Column(Text)
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(Text)
    processed_at = Column(Text)
    error = Column(Text)


class ScanSession(Base):
    __tablename__ = "scan_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_type = Column(Text)
    scan_time = Column(Text)
    scan_time_et = Column(Text)
    status = Column(Text)
    n_candidates = Column(Integer)
    n_signals = Column(Integer)
    duration_ms = Column(Integer)
    metadata_json = Column("metadata", Text)
    created_at = Column(Text)
