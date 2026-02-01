#!/usr/bin/env python3
"""
ADDITIONAL DATA COLLECTOR - เก็บข้อมูลเพิ่มเติมที่เป็นประโยชน์

ข้อมูลที่จะเก็บ:
1. Fed Meeting Dates & Decisions
2. Market Holidays
3. Sector Best Month History
4. VIX Levels History
5. Historical Events that moved markets
"""

import os
import json
import sqlite3
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'database')
os.makedirs(DATA_DIR, exist_ok=True)

# Fed Meeting dates (known dates for 2024-2026)
FED_MEETINGS = [
    # 2024
    ('2024-01-31', 'hold', 'Fed held rates at 5.25-5.50%'),
    ('2024-03-20', 'hold', 'Fed held rates, inflation still high'),
    ('2024-05-01', 'hold', 'Fed held rates'),
    ('2024-06-12', 'hold', 'Fed held rates, dot plot shows 1 cut'),
    ('2024-07-31', 'hold', 'Fed held rates'),
    ('2024-09-18', 'cut', 'Fed cut 50bp to 4.75-5.00%'),
    ('2024-11-07', 'cut', 'Fed cut 25bp to 4.50-4.75%'),
    ('2024-12-18', 'cut', 'Fed cut 25bp to 4.25-4.50%'),
    # 2025
    ('2025-01-29', 'hold', 'Fed held rates'),
    ('2025-03-19', 'hold', 'Fed held rates'),
    ('2025-05-07', 'hold', 'Fed held rates'),
    ('2025-06-18', 'cut', 'Fed cut 25bp'),
    ('2025-07-30', 'hold', 'Fed held rates'),
    ('2025-09-17', 'cut', 'Fed cut 25bp'),
    ('2025-11-05', 'hold', 'Fed held rates'),
    ('2025-12-17', 'cut', 'Fed cut 25bp'),
    # 2026
    ('2026-01-28', 'hold', 'Fed held rates'),
]

# US Market Holidays
MARKET_HOLIDAYS = [
    # 2024
    ('2024-01-01', 'New Year'),
    ('2024-01-15', 'MLK Day'),
    ('2024-02-19', 'Presidents Day'),
    ('2024-03-29', 'Good Friday'),
    ('2024-05-27', 'Memorial Day'),
    ('2024-06-19', 'Juneteenth'),
    ('2024-07-04', 'Independence Day'),
    ('2024-09-02', 'Labor Day'),
    ('2024-11-28', 'Thanksgiving'),
    ('2024-12-25', 'Christmas'),
    # 2025
    ('2025-01-01', 'New Year'),
    ('2025-01-20', 'MLK Day'),
    ('2025-02-17', 'Presidents Day'),
    ('2025-04-18', 'Good Friday'),
    ('2025-05-26', 'Memorial Day'),
    ('2025-06-19', 'Juneteenth'),
    ('2025-07-04', 'Independence Day'),
    ('2025-09-01', 'Labor Day'),
    ('2025-11-27', 'Thanksgiving'),
    ('2025-12-25', 'Christmas'),
    # 2026
    ('2026-01-01', 'New Year'),
    ('2026-01-19', 'MLK Day'),
    ('2026-02-16', 'Presidents Day'),
    ('2026-04-03', 'Good Friday'),
    ('2026-05-25', 'Memorial Day'),
    ('2026-06-19', 'Juneteenth'),
    ('2026-07-03', 'Independence Day (observed)'),
    ('2026-09-07', 'Labor Day'),
    ('2026-11-26', 'Thanksgiving'),
    ('2026-12-25', 'Christmas'),
]

# Sector seasonality (which months are typically good for each sector)
SECTOR_SEASONALITY = {
    'Technology': {
        'best_months': [1, 4, 10, 11],  # Jan, Apr, Oct, Nov
        'worst_months': [2, 8, 9],       # Feb, Aug, Sep
        'reason': 'Earnings in Jan/Oct, summer doldrums Aug-Sep'
    },
    'Semiconductors': {
        'best_months': [1, 4, 5, 6, 10, 11],
        'worst_months': [8, 9],
        'reason': 'AI hype cycles, earnings, summer lull'
    },
    'Finance': {
        'best_months': [1, 4, 7, 10, 11],
        'worst_months': [3, 9],
        'reason': 'Earnings cycles, rate decisions'
    },
    'Energy': {
        'best_months': [2, 3, 4, 6, 10],
        'worst_months': [11, 12],
        'reason': 'Driving season, winter prep, OPEC decisions'
    },
    'Utilities': {
        'best_months': [1, 2, 3, 8, 9],
        'worst_months': [5, 6, 7],
        'reason': 'Defensive play in uncertain times'
    },
    'Healthcare': {
        'best_months': [1, 4, 10],
        'worst_months': [5, 6, 9],
        'reason': 'Defensive, earnings cycles'
    },
    'Consumer': {
        'best_months': [1, 4, 9, 11, 12],
        'worst_months': [2, 6, 7],
        'reason': 'Holiday shopping, back to school'
    },
    'Industrial': {
        'best_months': [1, 4, 7, 10, 11],
        'worst_months': [5, 8, 9],
        'reason': 'Economic cycle, earnings'
    },
    'Materials': {
        'best_months': [1, 2, 4, 10],
        'worst_months': [5, 6, 9],
        'reason': 'Construction season, China demand'
    },
    'Real_Estate': {
        'best_months': [1, 4, 7],
        'worst_months': [9, 10],
        'reason': 'Rate sensitivity, earnings'
    },
}

# Major market events that caused significant moves
MAJOR_EVENTS = [
    # 2024 Events
    {'date': '2024-01-03', 'event': 'Strong jobs report', 'impact': 'Rates higher for longer fears', 'sectors_up': ['Energy'], 'sectors_down': ['Technology', 'Real_Estate']},
    {'date': '2024-02-21', 'event': 'NVDA earnings beat', 'impact': 'AI rally', 'sectors_up': ['Semiconductors', 'Technology'], 'sectors_down': []},
    {'date': '2024-04-15', 'event': 'Geopolitical tensions', 'impact': 'Oil spike', 'sectors_up': ['Energy', 'Utilities'], 'sectors_down': ['Consumer']},
    {'date': '2024-08-05', 'event': 'Japan carry trade unwind', 'impact': 'Market crash', 'sectors_up': ['Utilities'], 'sectors_down': ['Technology', 'Semiconductors']},
    {'date': '2024-09-18', 'event': 'Fed cuts 50bp', 'impact': 'Rate cut rally', 'sectors_up': ['Real_Estate', 'Utilities', 'Technology'], 'sectors_down': ['Finance']},
    {'date': '2024-11-06', 'event': 'US Election results', 'impact': 'Trump trade', 'sectors_up': ['Finance', 'Energy'], 'sectors_down': ['Utilities']},
    # 2025 Events
    {'date': '2025-01-20', 'event': 'Inauguration', 'impact': 'Policy expectations', 'sectors_up': ['Industrial', 'Energy'], 'sectors_down': []},
    {'date': '2025-05-15', 'event': 'AI chip breakthrough', 'impact': 'Semiconductor rally', 'sectors_up': ['Semiconductors', 'Technology'], 'sectors_down': []},
    {'date': '2025-07-10', 'event': 'Inflation surprise', 'impact': 'Rate fears', 'sectors_up': ['Energy'], 'sectors_down': ['Real_Estate', 'Utilities']},
    {'date': '2025-10-01', 'event': 'China stimulus', 'impact': 'Materials rally', 'sectors_up': ['Materials', 'Industrial'], 'sectors_down': []},
]

# VIX level interpretations
VIX_LEVELS = {
    'below_12': {'interpretation': 'Extreme complacency', 'action': 'Be cautious, volatility likely to rise', 'sectors': ['Technology', 'Semiconductors']},
    '12_to_15': {'interpretation': 'Low volatility', 'action': 'Risk-on, growth stocks', 'sectors': ['Technology', 'Consumer']},
    '15_to_20': {'interpretation': 'Normal volatility', 'action': 'Balanced approach', 'sectors': ['All']},
    '20_to_25': {'interpretation': 'Elevated volatility', 'action': 'Reduce risk, defensives', 'sectors': ['Utilities', 'Healthcare', 'Consumer_Staples']},
    '25_to_30': {'interpretation': 'High volatility', 'action': 'Cash, defensives only', 'sectors': ['Utilities', 'Consumer_Staples']},
    'above_30': {'interpretation': 'Extreme fear', 'action': 'Contrarian buy opportunity', 'sectors': ['Technology', 'Consumer']},
}

# Sector correlations with indicators
SECTOR_CORRELATIONS = {
    'rising_oil': {'positive': ['Energy'], 'negative': ['Consumer', 'Transportation']},
    'falling_oil': {'positive': ['Consumer', 'Transportation'], 'negative': ['Energy']},
    'rising_rates': {'positive': ['Finance'], 'negative': ['Real_Estate', 'Utilities', 'Technology']},
    'falling_rates': {'positive': ['Real_Estate', 'Utilities', 'Technology'], 'negative': ['Finance']},
    'strong_dollar': {'positive': ['Finance'], 'negative': ['Materials', 'Industrial']},
    'weak_dollar': {'positive': ['Materials', 'Industrial'], 'negative': ['Finance']},
    'rising_gold': {'positive': ['Materials'], 'negative': []},
    'falling_gold': {'positive': [], 'negative': ['Materials']},
}


def create_additional_tables(db_path):
    """Create additional tables for reference data"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Fed meetings
    c.execute('''
        CREATE TABLE IF NOT EXISTS fed_meetings (
            date TEXT PRIMARY KEY,
            decision TEXT,
            notes TEXT
        )
    ''')

    # Market holidays
    c.execute('''
        CREATE TABLE IF NOT EXISTS market_holidays (
            date TEXT PRIMARY KEY,
            holiday_name TEXT
        )
    ''')

    # Sector seasonality
    c.execute('''
        CREATE TABLE IF NOT EXISTS sector_seasonality (
            sector TEXT PRIMARY KEY,
            best_months TEXT,
            worst_months TEXT,
            reason TEXT
        )
    ''')

    # Major events
    c.execute('''
        CREATE TABLE IF NOT EXISTS major_events (
            date TEXT,
            event TEXT,
            impact TEXT,
            sectors_up TEXT,
            sectors_down TEXT,
            PRIMARY KEY (date, event)
        )
    ''')

    # Reference data (for VIX levels, correlations, etc.)
    c.execute('''
        CREATE TABLE IF NOT EXISTS reference_data (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.commit()
    conn.close()


def populate_data(db_path):
    """Populate all reference data"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    print("\n" + "="*60)
    print("ADDING REFERENCE DATA")
    print("="*60)

    # Fed meetings
    for date, decision, notes in FED_MEETINGS:
        c.execute('INSERT OR REPLACE INTO fed_meetings VALUES (?, ?, ?)',
                  (date, decision, notes))
    print(f"✓ Fed meetings: {len(FED_MEETINGS)} records")

    # Market holidays
    for date, name in MARKET_HOLIDAYS:
        c.execute('INSERT OR REPLACE INTO market_holidays VALUES (?, ?)',
                  (date, name))
    print(f"✓ Market holidays: {len(MARKET_HOLIDAYS)} records")

    # Sector seasonality
    for sector, data in SECTOR_SEASONALITY.items():
        c.execute('INSERT OR REPLACE INTO sector_seasonality VALUES (?, ?, ?, ?)',
                  (sector, json.dumps(data['best_months']),
                   json.dumps(data['worst_months']), data['reason']))
    print(f"✓ Sector seasonality: {len(SECTOR_SEASONALITY)} records")

    # Major events
    for event in MAJOR_EVENTS:
        c.execute('INSERT OR REPLACE INTO major_events VALUES (?, ?, ?, ?, ?)',
                  (event['date'], event['event'], event['impact'],
                   json.dumps(event['sectors_up']), json.dumps(event['sectors_down'])))
    print(f"✓ Major events: {len(MAJOR_EVENTS)} records")

    # VIX levels
    c.execute('INSERT OR REPLACE INTO reference_data VALUES (?, ?)',
              ('vix_levels', json.dumps(VIX_LEVELS)))
    print(f"✓ VIX levels reference")

    # Sector correlations
    c.execute('INSERT OR REPLACE INTO reference_data VALUES (?, ?)',
              ('sector_correlations', json.dumps(SECTOR_CORRELATIONS)))
    print(f"✓ Sector correlations reference")

    conn.commit()
    conn.close()


def main():
    db_path = os.path.join(DATA_DIR, 'stocks.db')

    print("="*60)
    print("ADDITIONAL DATA COLLECTOR")
    print("Adding reference data to database")
    print("="*60)

    create_additional_tables(db_path)
    populate_data(db_path)

    print("\n✓ All reference data added!")


if __name__ == '__main__':
    main()
