#!/usr/bin/env python3
"""
FULL UNIVERSE COLLECTOR - เก็บข้อมูล 680+ หุ้น

รวมหุ้นทั้งหมดจากทุก sector
"""

import os
import sqlite3
import pandas as pd
from datetime import datetime
import time
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    print("Need yfinance")
    yf = None

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'database')
os.makedirs(DATA_DIR, exist_ok=True)

# FULL UNIVERSE - 680+ stocks
FULL_UNIVERSE = {
    'Technology': [
        # Large Cap
        'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'META', 'AMZN', 'NFLX', 'CRM', 'ORCL', 'ADBE',
        'INTC', 'CSCO', 'IBM', 'INTU', 'NOW', 'PANW', 'SNOW', 'DDOG', 'ZS', 'CRWD',
        'NET', 'PLTR', 'WDAY', 'TEAM', 'MDB', 'OKTA', 'ZM', 'TWLO', 'DOCU', 'VEEV',
        'TTD', 'FTNT', 'ANSS', 'CDNS', 'SNPS', 'KEYS', 'MANH', 'PAYC', 'PCTY', 'HUBS',
        # Mid Cap
        'SHOP', 'SQ', 'PINS', 'SNAP', 'RBLX', 'U', 'COIN', 'PATH', 'CFLT', 'BILL',
        'DOCN', 'ESTC', 'GTLB', 'MNDY', 'ZI', 'APPN', 'NEWR', 'FROG', 'TOST', 'APP',
    ],
    'Semiconductors': [
        'NVDA', 'AMD', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX', 'KLAC', 'ADI',
        'MCHP', 'NXPI', 'ON', 'MRVL', 'SWKS', 'MPWR', 'ENTG', 'ASML', 'TSM', 'SNPS',
        'CDNS', 'QRVO', 'WOLF', 'CRUS', 'LSCC', 'RMBS', 'MKSI', 'FORM', 'ONTO', 'ACLS',
        'SITM', 'IPGP', 'ALGM', 'AMBA', 'DIOD', 'PLAB', 'SMTC', 'OLED', 'HIMX', 'KLIC',
    ],
    'Finance_Banks': [
        'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'USB', 'PNC', 'TFC', 'COF',
        'MTB', 'FITB', 'RF', 'KEY', 'CFG', 'HBAN', 'ZION', 'CMA', 'FHN', 'ALLY',
        'SIVB', 'SBNY', 'FRC', 'WAL', 'PACW', 'EWBC', 'BOH', 'BKU', 'UMBF', 'UBSI',
        'WTFC', 'PNFP', 'SFNC', 'GBCI', 'ABCB', 'CADE', 'FCNCA', 'SNV', 'BOKF', 'FNB',
    ],
    'Finance_Payments': [
        'V', 'MA', 'AXP', 'PYPL', 'GPN', 'FIS', 'FISV', 'CPAY', 'WU', 'AFRM',
        'SQ', 'TOST', 'PAYX', 'ADP', 'FOUR', 'PAYO', 'RPAY', 'PSFE', 'ACIW', 'SSNC',
    ],
    'Finance_Asset_Mgmt': [
        'BLK', 'SCHW', 'TROW', 'BEN', 'IVZ', 'NTRS', 'STT', 'BK', 'AMG', 'EV',
        'BX', 'KKR', 'APO', 'ARES', 'OWL', 'TPG', 'CG', 'HLNE', 'VCTR', 'STEP',
    ],
    'Finance_Insurance': [
        'CB', 'TRV', 'PGR', 'ALL', 'AFL', 'MET', 'PRU', 'HIG', 'AIG', 'LNC',
        'UNM', 'GL', 'KNSL', 'RNR', 'EG', 'ACGL', 'WRB', 'CINF', 'ORI', 'THG',
        'KMPR', 'AFG', 'FAF', 'FNF', 'SIGI', 'AIZ', 'RLI', 'UFCS', 'NSEC', 'HCI',
    ],
    'Finance_Exchanges': [
        'CME', 'ICE', 'NDAQ', 'CBOE', 'SPGI', 'MCO', 'MSCI', 'MKTX', 'TW', 'VIRT',
    ],
    'Industrial_Machinery': [
        'CAT', 'DE', 'AGCO', 'CNHI', 'CMI', 'PCAR', 'OSK', 'TTC', 'TEX', 'ALG',
        'IR', 'DOV', 'XYL', 'ITT', 'FLS', 'PH', 'GGG', 'FSS', 'MWA', 'CFX',
    ],
    'Industrial_Aerospace': [
        'BA', 'RTX', 'LMT', 'NOC', 'GD', 'TDG', 'HII', 'LHX', 'KTOS', 'AJRD',
        'SPR', 'TXT', 'HEI', 'AXON', 'BWXT', 'MRCY', 'CACI', 'LDOS', 'SAIC', 'BAH',
    ],
    'Industrial_Conglomerate': [
        'HON', 'GE', 'MMM', 'EMR', 'ETN', 'ITW', 'ROP', 'AME', 'NDSN', 'TT',
        'CARR', 'OTIS', 'JCI', 'GNRC', 'HUBB', 'AOS', 'ALLE', 'MAS', 'SWK', 'FAST',
    ],
    'Industrial_Transport': [
        'UNP', 'CSX', 'NSC', 'CP', 'CNI', 'KSU', 'FDX', 'UPS', 'EXPD', 'CHRW',
        'JBHT', 'XPO', 'SAIA', 'ODFL', 'WERN', 'KNX', 'SNDR', 'HUBG', 'ARCB', 'HTLD',
    ],
    'Healthcare_Pharma': [
        'JNJ', 'PFE', 'ABBV', 'MRK', 'LLY', 'BMY', 'AMGN', 'GILD', 'REGN', 'VRTX',
        'BIIB', 'MRNA', 'AZN', 'GSK', 'NVO', 'SNY', 'NVS', 'TAK', 'BNTX', 'JAZZ',
        'ALNY', 'INCY', 'EXEL', 'NBIX', 'UTHR', 'SRPT', 'BMRN', 'IONS', 'RARE', 'RPRX',
    ],
    'Healthcare_MedDevices': [
        'MDT', 'ABT', 'TMO', 'DHR', 'ISRG', 'SYK', 'BSX', 'EW', 'ZBH', 'HOLX',
        'DXCM', 'PODD', 'TFX', 'ALGN', 'IDXX', 'TECH', 'BIO', 'IQV', 'VEEV', 'MASI',
    ],
    'Healthcare_Services': [
        'UNH', 'ELV', 'CI', 'HUM', 'CNC', 'CVS', 'MCK', 'ABC', 'CAH', 'HCA',
        'THC', 'UHS', 'ACHC', 'DVA', 'ENSG', 'SGRY', 'MD', 'SEM', 'BHC', 'AMED',
    ],
    'Consumer_Retail': [
        'HD', 'LOW', 'TJX', 'ROST', 'DG', 'DLTR', 'BBY', 'TSCO', 'ORLY', 'AZO',
        'AAP', 'ULTA', 'RH', 'WSM', 'BURL', 'KSS', 'M', 'JWN', 'GPS', 'ANF',
        'URBN', 'LULU', 'DECK', 'CROX', 'GRMN', 'COLM', 'VFC', 'PVH', 'RL', 'TPR',
    ],
    'Consumer_Food': [
        'MCD', 'SBUX', 'YUM', 'CMG', 'DPZ', 'QSR', 'DRI', 'TXRH', 'WING', 'SHAK',
        'CAKE', 'EAT', 'DINE', 'PLAY', 'BJRI', 'BLMN', 'JACK', 'ARCO', 'LOCO', 'TACO',
    ],
    'Consumer_Travel': [
        'MAR', 'HLT', 'H', 'WH', 'CHH', 'ABNB', 'BKNG', 'EXPE', 'RCL', 'CCL',
        'NCLH', 'LVS', 'WYNN', 'MGM', 'CZR', 'DKNG', 'PENN', 'GDEN', 'MTN', 'SKX',
    ],
    'Consumer_Auto': [
        'TSLA', 'F', 'GM', 'TM', 'HMC', 'STLA', 'RIVN', 'LCID', 'NIO', 'XPEV',
        'LI', 'FSR', 'GOEV', 'WKHS', 'RIDE', 'NKLA', 'HYLN', 'ARVL', 'PSNY', 'FFIE',
    ],
    'Consumer_Staples': [
        'WMT', 'COST', 'TGT', 'KR', 'WBA', 'SYY', 'PG', 'KO', 'PEP', 'PM',
        'MO', 'CL', 'EL', 'KMB', 'GIS', 'K', 'HSY', 'MDLZ', 'SJM', 'CAG',
        'CPB', 'HRL', 'TSN', 'KHC', 'CHD', 'CLX', 'USFD', 'PFGC', 'SFM', 'CHEF',
    ],
    'Energy_Oil': [
        'XOM', 'CVX', 'COP', 'EOG', 'OXY', 'DVN', 'FANG', 'APA', 'OVV', 'CTRA',
        'MTDR', 'PR', 'SM', 'MGY', 'CHRD', 'CLR', 'NOG', 'ET', 'EPD', 'TRGP',
        'PDCE', 'ESTE', 'REI', 'CPE', 'ROCC', 'VTLE', 'GPOR', 'BRY', 'RRC', 'SWN',
    ],
    'Energy_Services': [
        'SLB', 'HAL', 'BKR', 'NOV', 'FTI', 'CHX', 'HP', 'PTEN', 'NBR', 'OII',
        'WHD', 'LBRT', 'DRQ', 'XPRO', 'NESR', 'GTLS', 'SOC', 'NR', 'PUMP', 'AROC',
    ],
    'Energy_Refining': [
        'MPC', 'VLO', 'PSX', 'DK', 'PBF', 'PARR', 'HFC', 'CLMT', 'CVI', 'INT',
    ],
    'Energy_Midstream': [
        'WMB', 'KMI', 'OKE', 'ET', 'EPD', 'MPLX', 'PAA', 'TRGP', 'ENB', 'TRP',
        'WES', 'AM', 'DTM', 'ETRN', 'KNTK', 'GEL', 'NS', 'USAC', 'SMLP', 'MPLX',
    ],
    'Utilities_Electric': [
        'NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'ED', 'PEG',
        'WEC', 'ES', 'DTE', 'AEE', 'CMS', 'LNT', 'NI', 'EVRG', 'ATO', 'FE',
        'PPL', 'CNP', 'ETR', 'NRG', 'CEG', 'VST', 'PNW', 'IDA', 'OGE', 'AVA',
    ],
    'Utilities_Water': [
        'AWK', 'WTR', 'AWR', 'CWT', 'SJW', 'YORW', 'MSEX', 'ARTNA',
    ],
    'Utilities_Gas': [
        'NJR', 'OGS', 'SWX', 'SR', 'SPH', 'NWN', 'UTL',
    ],
    'Real_Estate_Industrial': [
        'PLD', 'DRE', 'STAG', 'FR', 'REXR', 'TRNO', 'EGP', 'GTY',
    ],
    'Real_Estate_Office': [
        'BXP', 'VNO', 'KRC', 'DEI', 'HPP', 'SLG', 'PGRE', 'CUZ', 'JBG', 'PDM',
    ],
    'Real_Estate_Retail': [
        'SPG', 'O', 'REG', 'KIM', 'FRT', 'BRX', 'KRG', 'SITE', 'ROIC', 'AKR',
    ],
    'Real_Estate_Residential': [
        'AVB', 'EQR', 'MAA', 'UDR', 'ESS', 'CPT', 'AIV', 'NXRT', 'IRT', 'ELS',
    ],
    'Real_Estate_Data': [
        'EQIX', 'DLR', 'AMT', 'CCI', 'SBAC', 'UNIT', 'CONE', 'CCOI', 'LMND',
    ],
    'Real_Estate_Healthcare': [
        'WELL', 'VTR', 'PEAK', 'OHI', 'HR', 'NHI', 'SBRA', 'DHC', 'LTC', 'CTRE',
    ],
    'Real_Estate_Storage': [
        'PSA', 'EXR', 'CUBE', 'LSI', 'NSA', 'JCAP',
    ],
    'Materials_Chemicals': [
        'LIN', 'APD', 'SHW', 'ECL', 'DD', 'DOW', 'PPG', 'EMN', 'CE', 'ALB',
        'IFF', 'FMC', 'CF', 'MOS', 'NTR', 'LYB', 'OLN', 'CC', 'AXTA', 'RPM',
    ],
    'Materials_Metals': [
        'FCX', 'NEM', 'NUE', 'STLD', 'CLF', 'X', 'AA', 'ATI', 'CMC', 'RS',
        'WOR', 'CRS', 'ZEUS', 'CENX', 'KALU', 'HCC', 'HAYN', 'SCHN', 'SXC',
    ],
    'Materials_Construction': [
        'MLM', 'VMC', 'EXP', 'SUM', 'ITE', 'ROCK', 'US', 'USLM',
    ],
    'Materials_Packaging': [
        'BALL', 'CCK', 'AVY', 'SEE', 'BLL', 'SON', 'PKG', 'IP', 'WRK', 'GPK',
    ],
    'Telecom': [
        'T', 'VZ', 'TMUS', 'LUMN', 'USM', 'SHEN', 'ATUS', 'LBRDK', 'GNCMA', 'WOW',
    ],
    'Media': [
        'DIS', 'CMCSA', 'WBD', 'PARA', 'FOX', 'FOXA', 'NWSA', 'NWS', 'NYT', 'OMC',
        'IPG', 'MGID', 'CCO', 'SSP', 'GCI', 'LEG', 'LTRPA', 'LGF.A', 'LGF.B', 'MSGS',
    ],
}

def count_universe():
    """Count total stocks in universe"""
    total = 0
    for sector, symbols in FULL_UNIVERSE.items():
        total += len(symbols)
        print(f"  {sector}: {len(symbols)} stocks")
    print(f"\n  TOTAL: {total} stocks")
    return total


def collect_batch(symbols, sector, db_path, period='2y'):
    """Collect a batch of stocks"""
    conn = sqlite3.connect(db_path)
    collected = 0
    failed = []

    for symbol in symbols:
        try:
            data = yf.download(symbol, period=period, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            if len(data) > 0:
                for idx, row in data.iterrows():
                    date_str = idx.strftime('%Y-%m-%d')
                    conn.execute('''
                        INSERT OR REPLACE INTO stock_prices
                        (symbol, date, open, high, low, close, volume, sector)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        symbol, date_str,
                        float(row['Open']), float(row['High']),
                        float(row['Low']), float(row['Close']),
                        int(row['Volume']), sector
                    ))
                collected += 1
            else:
                failed.append(symbol)

        except Exception as e:
            failed.append(symbol)
            continue

        # Small delay to avoid rate limiting
        time.sleep(0.1)

    conn.commit()
    conn.close()
    return collected, failed


def main():
    """Collect full universe"""
    print("="*70)
    print("FULL UNIVERSE COLLECTOR - 680+ Stocks")
    print("="*70)

    print("\nUniverse breakdown:")
    total = count_universe()

    db_path = os.path.join(DATA_DIR, 'stocks.db')

    print("\n" + "="*70)
    print("Starting data collection...")
    print("="*70)

    all_collected = 0
    all_failed = []

    for sector, symbols in FULL_UNIVERSE.items():
        print(f"\n{sector}: {len(symbols)} stocks...", end=' ', flush=True)
        collected, failed = collect_batch(symbols, sector, db_path)
        all_collected += collected
        all_failed.extend(failed)
        print(f"Done ({collected}/{len(symbols)})")

    print("\n" + "="*70)
    print("COLLECTION COMPLETE")
    print("="*70)
    print(f"\nCollected: {all_collected}/{total} stocks")
    print(f"Failed: {len(all_failed)}")

    if all_failed:
        print(f"\nFailed symbols: {', '.join(all_failed[:20])}{'...' if len(all_failed) > 20 else ''}")

    # Show database summary
    conn = sqlite3.connect(db_path)
    cursor = conn.execute('SELECT COUNT(DISTINCT symbol), COUNT(*) FROM stock_prices')
    row = cursor.fetchone()
    conn.close()

    print(f"\nDatabase now has: {row[0]} symbols, {row[1]:,} records")


if __name__ == '__main__':
    main()
