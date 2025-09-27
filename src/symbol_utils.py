"""
Symbol Utilities
ยูทิลิตี้สำหรับจัดการ stock symbols และ ETF detection
"""

from typing import Dict, Any, Optional, List


class SymbolUtils:
    """Utilities for stock symbol handling and ETF detection"""

    # Common ETF prefixes and suffixes
    ETF_PATTERNS = {
        'prefixes': ['SPY', 'QQQ', 'IWM', 'EFA', 'EEM', 'VTI', 'VOO', 'IVV', 'VEA', 'VWO'],
        'suffixes': [],
        'keywords': ['ETF', 'FUND', 'TRUST', 'INDEX']
    }

    # Well-known ETFs
    KNOWN_ETFS = {
        # S&P 500 ETFs
        'SPY': 'SPDR S&P 500 ETF',
        'VOO': 'Vanguard S&P 500 ETF',
        'IVV': 'iShares Core S&P 500 ETF',
        'SPYG': 'SPDR Portfolio S&P 500 Growth ETF',
        'SPYV': 'SPDR Portfolio S&P 500 Value ETF',
        'SPYI': 'SPDR Portfolio S&P 500 High Dividend ETF',

        # Tech ETFs
        'QQQ': 'Invesco QQQ ETF',
        'QQQM': 'Invesco NASDAQ 100 ETF',
        'XLK': 'Technology Select Sector SPDR Fund',
        'VGT': 'Vanguard Information Technology ETF',
        'FTEC': 'Fidelity MSCI Information Technology ETF',

        # Dividend ETFs
        'VYM': 'Vanguard High Dividend Yield ETF',
        'SCHD': 'Schwab US Dividend Equity ETF',
        'DVY': 'iShares Select Dividend ETF',
        'HDV': 'iShares High Dividend ETF',
        'NOBL': 'ProShares S&P 500 Dividend Aristocrats ETF',
        'JEPI': 'JPMorgan Equity Premium Income ETF',
        'QYLD': 'Global X NASDAQ 100 Covered Call ETF',
        'DIVO': 'Amplify CWP Enhanced Dividend Income ETF',

        # Broad Market ETFs
        'VTI': 'Vanguard Total Stock Market ETF',
        'ITOT': 'iShares Core S&P Total U.S. Stock Market ETF',
        'SWTSX': 'Schwab Total Stock Market Index Fund',

        # Small/Mid Cap ETFs
        'IWM': 'iShares Russell 2000 ETF',
        'VB': 'Vanguard Small-Cap ETF',
        'VTW': 'Vanguard Russell 2000 ETF',
        'MDY': 'SPDR S&P MidCap 400 ETF',

        # International ETFs
        'EFA': 'iShares MSCI EAFE ETF',
        'EEM': 'iShares MSCI Emerging Markets ETF',
        'VEA': 'Vanguard FTSE Developed Markets ETF',
        'VWO': 'Vanguard FTSE Emerging Markets ETF',
        'ACWI': 'iShares MSCI ACWI ETF',

        # Sector ETFs
        'XLF': 'Financial Select Sector SPDR Fund',
        'XLE': 'Energy Select Sector SPDR Fund',
        'XLV': 'Health Care Select Sector SPDR Fund',
        'XLI': 'Industrial Select Sector SPDR Fund',
        'XLP': 'Consumer Staples Select Sector SPDR Fund',
        'XLY': 'Consumer Discretionary Select Sector SPDR Fund',
        'XLU': 'Utilities Select Sector SPDR Fund',
        'XLB': 'Materials Select Sector SPDR Fund',
        'XLRE': 'Real Estate Select Sector SPDR Fund',

        # Bond ETFs
        'BND': 'Vanguard Total Bond Market ETF',
        'AGG': 'iShares Core U.S. Aggregate Bond ETF',
        'TLT': 'iShares 20+ Year Treasury Bond ETF',
        'SHY': 'iShares 1-3 Year Treasury Bond ETF',

        # Commodity ETFs
        'GLD': 'SPDR Gold Shares ETF',
        'SLV': 'iShares Silver Trust ETF',
        'USO': 'United States Oil Fund ETF',
        'DBA': 'Invesco DB Agriculture Fund',

        # Volatility ETFs
        'VIX': 'iPath S&P 500 VIX Short-Term Futures ETN',
        'UVXY': 'ProShares Ultra VIX Short-Term Futures ETF',
        'SVXY': 'ProShares Short VIX Short-Term Futures ETF'
    }

    @classmethod
    def is_etf(cls, symbol: str) -> bool:
        """
        Check if a symbol is an ETF

        Args:
            symbol: Stock symbol to check

        Returns:
            True if symbol is likely an ETF
        """
        symbol = symbol.upper().strip()

        # Check known ETFs first
        if symbol in cls.KNOWN_ETFS:
            return True

        # Check common ETF patterns
        for prefix in cls.ETF_PATTERNS['prefixes']:
            if symbol.startswith(prefix):
                return True

        # Check for ETF keywords in symbol
        for keyword in cls.ETF_PATTERNS['keywords']:
            if keyword in symbol:
                return True

        return False

    @classmethod
    def get_etf_info(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get ETF information if available

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with ETF info or None if not an ETF
        """
        symbol = symbol.upper().strip()

        if not cls.is_etf(symbol):
            return None

        return {
            'symbol': symbol,
            'is_etf': True,
            'name': cls.KNOWN_ETFS.get(symbol, f'{symbol} ETF'),
            'type': cls._get_etf_type(symbol)
        }

    @classmethod
    def _get_etf_type(cls, symbol: str) -> str:
        """
        Determine ETF type based on symbol

        Args:
            symbol: ETF symbol

        Returns:
            ETF type string
        """
        symbol = symbol.upper()

        # Dividend ETFs
        dividend_etfs = ['VYM', 'SCHD', 'DVY', 'HDV', 'NOBL', 'JEPI', 'QYLD', 'DIVO', 'SPYI']
        if symbol in dividend_etfs:
            return 'Dividend ETF'

        # Tech ETFs
        tech_etfs = ['QQQ', 'QQQM', 'XLK', 'VGT', 'FTEC']
        if symbol in tech_etfs:
            return 'Technology ETF'

        # S&P 500 ETFs
        sp500_etfs = ['SPY', 'VOO', 'IVV', 'SPYG', 'SPYV']
        if symbol in sp500_etfs:
            return 'S&P 500 ETF'

        # Broad Market ETFs
        broad_etfs = ['VTI', 'ITOT', 'SWTSX']
        if symbol in broad_etfs:
            return 'Broad Market ETF'

        # Sector ETFs
        sector_etfs = ['XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLU', 'XLB', 'XLRE']
        if symbol in sector_etfs:
            return 'Sector ETF'

        # International ETFs
        intl_etfs = ['EFA', 'EEM', 'VEA', 'VWO', 'ACWI']
        if symbol in intl_etfs:
            return 'International ETF'

        # Small/Mid Cap ETFs
        smallcap_etfs = ['IWM', 'VB', 'VTW', 'MDY']
        if symbol in smallcap_etfs:
            return 'Small/Mid-Cap ETF'

        # Bond ETFs
        bond_etfs = ['BND', 'AGG', 'TLT', 'SHY']
        if symbol in bond_etfs:
            return 'Bond ETF'

        # Commodity ETFs
        commodity_etfs = ['GLD', 'SLV', 'USO', 'DBA']
        if symbol in commodity_etfs:
            return 'Commodity ETF'

        # Volatility ETFs
        vol_etfs = ['VIX', 'UVXY', 'SVXY']
        if symbol in vol_etfs:
            return 'Volatility ETF'

        return 'ETF'

    @classmethod
    def format_symbol_with_label(cls, symbol: str, include_name: bool = False) -> str:
        """
        Format symbol with ETF label if applicable

        Args:
            symbol: Stock symbol
            include_name: Whether to include full name

        Returns:
            Formatted symbol string with labels
        """
        symbol = symbol.upper().strip()
        etf_info = cls.get_etf_info(symbol)

        if etf_info:
            if include_name:
                return f"{symbol} <span class='badge bg-info ms-1'>ETF</span><br><small class='text-muted'>{etf_info['name']}</small>"
            else:
                return f"{symbol} <span class='badge bg-info ms-1'>ETF</span>"

        return symbol

    @classmethod
    def get_sample_symbols_with_etfs(cls) -> List[str]:
        """
        Get sample symbols including both stocks and ETFs

        Returns:
            List of sample symbols
        """
        return [
            # Individual Stocks
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
            # ETFs
            'SPY', 'QQQ', 'VYM', 'SCHD', 'VTI', 'IWM'
        ]


def test_symbol_utils():
    """Test the SymbolUtils functionality"""
    test_symbols = ['AAPL', 'SPY', 'QQQ', 'VYM', 'MSFT', 'SCHD', 'INVALID']

    print("=== Testing Symbol Utils ===")
    for symbol in test_symbols:
        is_etf = SymbolUtils.is_etf(symbol)
        etf_info = SymbolUtils.get_etf_info(symbol)
        formatted = SymbolUtils.format_symbol_with_label(symbol, include_name=True)

        print(f"\n{symbol}:")
        print(f"  Is ETF: {is_etf}")
        print(f"  ETF Info: {etf_info}")
        print(f"  Formatted: {formatted}")


if __name__ == "__main__":
    test_symbol_utils()