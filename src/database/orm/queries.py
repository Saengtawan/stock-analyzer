"""Common query helpers — replace raw SQL patterns across the project.

Usage:
    from database.orm.queries import get_latest_macro, get_active_positions

    macro = get_latest_macro()
    positions = get_active_positions()
"""
from database.orm.base import get_session
from database.orm.models import (
    MacroSnapshot, MarketBreadth, StockFundamentals, StockOHLC,
    ActivePosition, DiscoveryPick, NewsEvent, SectorETFReturn,
    EarningsHistory, AnalystRating, InsiderTransaction,
    IntradayBar5m, EngineHeartbeat,
)


def get_latest_macro():
    """Get most recent macro snapshot."""
    with get_session() as s:
        return s.query(MacroSnapshot).order_by(MacroSnapshot.date.desc()).first()


def get_latest_breadth():
    """Get most recent market breadth."""
    with get_session() as s:
        return s.query(MarketBreadth).order_by(MarketBreadth.date.desc()).first()


def get_active_positions():
    """Get all open positions."""
    with get_session() as s:
        return s.query(ActivePosition).all()


def get_active_discovery_picks():
    """Get active discovery picks sorted by score."""
    with get_session() as s:
        return s.query(DiscoveryPick).filter(
            DiscoveryPick.status == 'active'
        ).order_by(DiscoveryPick.layer2_score.desc()).all()


def get_stock_ohlc(symbol, start_date=None, end_date=None):
    """Get OHLCV for a symbol."""
    with get_session() as s:
        q = s.query(StockOHLC).filter(StockOHLC.symbol == symbol)
        if start_date:
            q = q.filter(StockOHLC.date >= start_date)
        if end_date:
            q = q.filter(StockOHLC.date <= end_date)
        return q.order_by(StockOHLC.date).all()


def get_sector_returns(date):
    """Get sector ETF returns for a date."""
    with get_session() as s:
        return s.query(SectorETFReturn).filter(
            SectorETFReturn.date == date
        ).all()


def get_news_for_symbol(symbol, start_date=None, end_date=None):
    """Get news events for a symbol."""
    with get_session() as s:
        q = s.query(NewsEvent).filter(NewsEvent.symbol == symbol)
        if start_date:
            q = q.filter(NewsEvent.scan_date_et >= start_date)
        if end_date:
            q = q.filter(NewsEvent.scan_date_et <= end_date)
        return q.order_by(NewsEvent.published_at.desc()).all()


def get_fundamentals(symbol):
    """Get stock fundamentals."""
    with get_session() as s:
        return s.query(StockFundamentals).filter(
            StockFundamentals.symbol == symbol
        ).first()


def get_all_fundamentals(min_volume=0, min_mcap=0):
    """Get all stock fundamentals with filters."""
    with get_session() as s:
        q = s.query(StockFundamentals)
        if min_volume:
            q = q.filter(StockFundamentals.avg_volume > min_volume)
        if min_mcap:
            q = q.filter(StockFundamentals.market_cap > min_mcap)
        return q.all()


def upsert_position(pos_dict):
    """Insert or update a position."""
    with get_session() as s:
        existing = s.query(ActivePosition).filter(
            ActivePosition.symbol == pos_dict['symbol']
        ).first()
        if existing:
            for k, v in pos_dict.items():
                setattr(existing, k, v)
        else:
            s.add(ActivePosition(**pos_dict))


def delete_position(symbol):
    """Delete a position."""
    with get_session() as s:
        s.query(ActivePosition).filter(
            ActivePosition.symbol == symbol
        ).delete()
